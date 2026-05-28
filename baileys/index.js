// ============================================================
// JIS-AI — Baileys WhatsApp Gateway
// কাজ:
//   ১. WhatsApp থেকে message আসলে → FastAPI /webhook/baileys এ পাঠাও
//   ২. FastAPI থেকে /send request আসলে → WhatsApp এ পাঠাও
//   ৩. /qr endpoint এ QR code দেখাও (প্রথমবার setup এর জন্য)
// ============================================================

require('dotenv').config();

const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion,
    makeCacheableSignalKeyStore,
    isJidBroadcast
} = require('@whiskeysockets/baileys');

const { Boom }  = require('@hapi/boom');
const express   = require('express');
const axios     = require('axios');
const pino      = require('pino');
const QRCode    = require('qrcode');
const path      = require('path');
const fs        = require('fs');

// ─── Config ────────────────────────────────────────────────

const PORT         = process.env.BAILEYS_PORT  || 3001;
const FASTAPI_URL  = process.env.FASTAPI_URL   || 'http://localhost:8000';
const API_SECRET   = process.env.API_SECRET    || 'change-this-secret';
const AUTH_FOLDER  = process.env.AUTH_FOLDER   || '/data/baileys_auth';  // Railway persistent disk

// ─── Auth folder তৈরি ──────────────────────────────────────

fs.mkdirSync(AUTH_FOLDER, { recursive: true });

// ─── State ─────────────────────────────────────────────────

let sock        = null;
let isConnected = false;
let currentQR   = null;
let reconnectTimer = null;

const logger = pino({ level: 'silent' });

// ─── Express App ───────────────────────────────────────────

const app = express();
app.use(express.json());

// ─── API Key চেক ───────────────────────────────────────────

const checkSecret = (req, res, next) => {
    const key = req.headers['x-api-secret'] || req.body?.api_secret;
    if (key !== API_SECRET) {
        return res.status(401).json({ error: 'Unauthorized' });
    }
    next();
};

// ─── Phone Format ──────────────────────────────────────────

const formatJid = (phone) => {
    let digits = String(phone).replace(/\D/g, '');
    if (digits.startsWith('01') && digits.length === 11) digits = '880' + digits;
    if (digits.startsWith('00')) digits = digits.slice(2);
    return `${digits}@s.whatsapp.net`;
};

// ─── WhatsApp Connect ──────────────────────────────────────

const connectWhatsApp = async () => {
    try {
        const { version }          = await fetchLatestBaileysVersion();
        const { state, saveCreds } = await useMultiFileAuthState(AUTH_FOLDER);

        sock = makeWASocket({
            version,
            logger,
            auth: {
                creds: state.creds,
                keys:  makeCacheableSignalKeyStore(state.keys, logger)
            },
            browser:           ['JIS-AI', 'Chrome', '120.0'],
            printQRInTerminal: true,
            syncFullHistory:   false,
            generateHighQualityLinkPreview: false,
        });

        // ── Connection Update ────────────────────────────────

        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) {
                currentQR = qr;
                console.log('\n📱 QR Ready — http://localhost:' + PORT + '/qr\n');
            }

            if (connection === 'open') {
                isConnected = true;
                currentQR   = null;
                console.log('✅ WhatsApp কানেক্টেড!');
            }

            if (connection === 'close') {
                isConnected = false;
                const code  = new Boom(lastDisconnect?.error)?.output?.statusCode;

                if (code === DisconnectReason.loggedOut) {
                    console.warn('⚠️ লগআউট হয়েছে। AUTH_FOLDER মুছে আবার চালান।');
                    fs.rmSync(AUTH_FOLDER, { recursive: true, force: true });
                    fs.mkdirSync(AUTH_FOLDER, { recursive: true });
                } else {
                    console.log(`🔄 বিচ্ছিন্ন (${code})। ৫ সেকেন্ড পরে reconnect...`);
                    clearTimeout(reconnectTimer);
                    reconnectTimer = setTimeout(connectWhatsApp, 5_000);
                }
            }
        });

        // ── Credentials Save ─────────────────────────────────

        sock.ev.on('creds.update', saveCreds);

        // ── Incoming Message → FastAPI ────────────────────────

        sock.ev.on('messages.upsert', async ({ messages, type }) => {
            if (type !== 'notify') return;

            for (const msg of messages) {
                // নিজের message বা broadcast skip
                if (msg.key.fromMe) continue;
                if (isJidBroadcast(msg.key.remoteJid)) continue;

                const phone = msg.key.remoteJid.replace('@s.whatsapp.net', '');
                const text  = msg.message?.conversation
                           || msg.message?.extendedTextMessage?.text
                           || '';

                if (!text) continue;

                console.log(`📨 আসা message [${phone}]: ${text.slice(0, 50)}`);

                // FastAPI /webhook/baileys এ পাঠাও
                try {
                    const { data } = await axios.post(
                        `${FASTAPI_URL}/webhook/baileys`,
                        { from: phone, message: text },
                        { timeout: 15_000 }
                    );

                    // AI reply থাকলে WhatsApp এ পাঠাও
                    if (data?.reply) {
                        await sock.sendMessage(
                            msg.key.remoteJid,
                            { text: data.reply }
                        );
                        console.log(`📤 AI reply পাঠানো → ${phone}`);
                    }
                } catch (err) {
                    console.error(`❌ FastAPI error:`, err.message);
                }
            }
        });

    } catch (err) {
        console.error('❌ Connect error:', err.message);
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(connectWhatsApp, 10_000);
    }
};

// ============================================================
// Express Endpoints
// ============================================================

// ── QR Code দেখাও (browser এ) ────────────────────────────────

app.get('/qr', async (req, res) => {
    if (isConnected) {
        return res.send(`
            <html><body style="font-family:sans-serif;text-align:center;padding:50px">
            <h2 style="color:green">✅ WhatsApp কানেক্টেড!</h2>
            <p>Baileys gateway চলছে।</p>
            </body></html>
        `);
    }

    if (!currentQR) {
        return res.send(`
            <html><body style="font-family:sans-serif;text-align:center;padding:50px">
            <h2>⏳ QR তৈরি হচ্ছে...</h2>
            <p>৩০ সেকেন্ড পরে refresh করুন।</p>
            <script>setTimeout(()=>location.reload(), 5000)</script>
            </body></html>
        `);
    }

    try {
        const qrImage = await QRCode.toDataURL(currentQR);
        res.send(`
            <html><body style="font-family:sans-serif;text-align:center;padding:30px;background:#f0f0f0">
            <h2>📱 WhatsApp QR স্ক্যান করুন</h2>
            <p>WhatsApp → Linked Devices → Link a Device</p>
            <img src="${qrImage}" style="width:300px;height:300px;border:4px solid #25D366;border-radius:12px"/>
            <p style="color:#888;font-size:13px">QR expire হলে page refresh করুন</p>
            <script>setTimeout(()=>location.reload(), 30000)</script>
            </body></html>
        `);
    } catch (err) {
        res.status(500).send('QR তৈরিতে সমস্যা হয়েছে');
    }
});

// ── Message পাঠাও (FastAPI/NovaTech থেকে call আসবে) ──────────

app.post('/send', checkSecret, async (req, res) => {
    const { phone, message } = req.body;

    if (!phone || !message) {
        return res.status(400).json({ error: 'phone এবং message দিন' });
    }

    if (!isConnected) {
        return res.status(503).json({ error: 'WhatsApp এখনো connect হয়নি', qr: '/qr' });
    }

    try {
        const jid = formatJid(phone);
        await sock.sendMessage(jid, { text: message });
        console.log(`✅ Message পাঠানো → ${phone}`);
        res.json({ success: true, phone, jid });
    } catch (err) {
        console.error(`❌ Send error:`, err.message);
        res.status(500).json({ error: err.message });
    }
});

// ── Status ───────────────────────────────────────────────────

app.get('/status', (req, res) => {
    res.json({
        connected:  isConnected,
        hasQR:      !!currentQR,
        qrUrl:      isConnected ? null : '/qr',
        service:    'JIS-AI Baileys Gateway',
    });
});

// ── Health ───────────────────────────────────────────────────

app.get('/health', (req, res) => {
    res.json({ status: 'running ✅', connected: isConnected });
});

// ─── Start ─────────────────────────────────────────────────

app.listen(PORT, () => {
    console.log(`🚀 Baileys Gateway চলছে → port ${PORT}`);
    console.log(`📱 QR দেখতে: http://localhost:${PORT}/qr`);
    connectWhatsApp();
});
