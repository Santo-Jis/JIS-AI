// ============================================================
// JIS-AI — Baileys WhatsApp Gateway (আপডেট)
//
// নতুন কি যোগ হয়েছে:
//   ✅ /send-image  → ছবি + caption পাঠানো
//   ✅ /send-product → পণ্যের ছবি ও বিবরণ একসাথে
//   বাকি সব আগের মতোই
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
const PORT        = process.env.BAILEYS_PORT || 3001;
const FASTAPI_URL = process.env.FASTAPI_URL  || 'http://localhost:8000';
const API_SECRET  = process.env.API_SECRET   || 'change-this-secret';
const AUTH_FOLDER = process.env.AUTH_FOLDER  || '/data/baileys_auth';

fs.mkdirSync(AUTH_FOLDER, { recursive: true });

let sock        = null;
let isConnected = false;
let currentQR   = null;

const logger = pino({ level: 'silent' });
const app    = express();
app.use(express.json());

// ─── Auth Middleware ────────────────────────────────────────
const checkSecret = (req, res, next) => {
    const key = req.headers['x-api-secret'] || req.body?.api_secret;
    if (key !== API_SECRET) return res.status(401).json({ error: 'Unauthorized' });
    next();
};

// ─── Phone Format ───────────────────────────────────────────
const formatJid = (phone) => {
    let digits = String(phone).replace(/\D/g, '');
    if (digits.startsWith('01') && digits.length === 11) digits = '880' + digits;
    if (digits.startsWith('00')) digits = digits.slice(2);
    return `${digits}@s.whatsapp.net`;
};

// ─── Image Buffer Helper ────────────────────────────────────
// URL থেকে image download করে Buffer বানায়
const fetchImageBuffer = async (imageUrl) => {
    const response = await axios.get(imageUrl, {
        responseType: 'arraybuffer',
        timeout: 10000,
        headers: { 'User-Agent': 'JIS-AI/1.0' }
    });
    return Buffer.from(response.data);
};

// ─── WhatsApp Connect ───────────────────────────────────────
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

        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;
            if (qr) {
                currentQR = qr;
                console.log('\n📱 QR Ready — http://localhost:' + PORT + '/qr\n');
            }
            if (connection === 'open') {
                isConnected = true;
                currentQR   = null;
                console.log('✅ WhatsApp Connected!');
            }
            if (connection === 'close') {
                isConnected = false;
                const shouldReconnect =
                    lastDisconnect?.error instanceof Boom &&
                    lastDisconnect.error.output.statusCode !== DisconnectReason.loggedOut;
                if (shouldReconnect) {
                    console.log('🔄 Reconnecting...');
                    setTimeout(connectWhatsApp, 5000);
                } else {
                    console.log('❌ Logged out. QR scan করুন।');
                }
            }
        });

        sock.ev.on('creds.update', saveCreds);

        // ── Incoming Message Handler ─────────────────────────
        sock.ev.on('messages.upsert', async ({ messages, type }) => {
            if (type !== 'notify') return;
            for (const msg of messages) {
                if (msg.key.fromMe) continue;
                if (isJidBroadcast(msg.key.remoteJid)) continue;

                const phone = msg.key.remoteJid.replace('@s.whatsapp.net', '');
                const text  = msg.message?.conversation ||
                              msg.message?.extendedTextMessage?.text || '';

                if (!text) continue;

                console.log(`📩 Message from ${phone}: ${text}`);

                try {
                    await axios.post(`${FASTAPI_URL}/webhook/baileys`, {
                        from:    phone,
                        message: text,
                    }, {
                        headers: { 'x-api-secret': API_SECRET },
                        timeout: 30000,
                    });
                } catch (err) {
                    console.error('❌ FastAPI forward error:', err.message);
                }
            }
        });

    } catch (err) {
        console.error('❌ WhatsApp connect error:', err.message);
        setTimeout(connectWhatsApp, 10000);
    }
};

connectWhatsApp();

// ============================================================
// ── API Routes ───────────────────────────────────────────────
// ============================================================

// ── 1. Text Message (আগের মতোই) ────────────────────────────
app.post('/send', checkSecret, async (req, res) => {
    const { phone, message } = req.body;
    if (!phone || !message)
        return res.status(400).json({ error: 'phone এবং message দিন' });
    if (!isConnected)
        return res.status(503).json({ error: 'WhatsApp connect হয়নি', qr: '/qr' });

    try {
        await sock.sendMessage(formatJid(phone), { text: message });
        console.log(`✅ Text → ${phone}`);
        res.json({ success: true });
    } catch (err) {
        console.error('❌ Send error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ── 2. Image Message (নতুন) ────────────────────────────────
// Body: { phone, image_url, caption }
app.post('/send-image', checkSecret, async (req, res) => {
    const { phone, image_url, caption } = req.body;

    if (!phone || !image_url)
        return res.status(400).json({ error: 'phone এবং image_url দিন' });
    if (!isConnected)
        return res.status(503).json({ error: 'WhatsApp connect হয়নি' });

    try {
        const jid    = formatJid(phone);
        const buffer = await fetchImageBuffer(image_url);

        await sock.sendMessage(jid, {
            image:   buffer,
            caption: caption || '',
            mimetype: 'image/jpeg',
        });

        console.log(`✅ Image → ${phone}`);
        res.json({ success: true });
    } catch (err) {
        console.error('❌ Image send error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ── 3. Product Card (নতুন — ছবি + formatted caption) ───────
// Body: { phone, product: { name, price, stock, description, image_url, unit } }
app.post('/send-product', checkSecret, async (req, res) => {
    const { phone, product } = req.body;

    if (!phone || !product)
        return res.status(400).json({ error: 'phone এবং product দিন' });
    if (!isConnected)
        return res.status(503).json({ error: 'WhatsApp connect হয়নি' });

    try {
        const jid = formatJid(phone);

        // Caption তৈরি করো
        const stockText = product.stock > 0
            ? `✅ স্টকে আছে (${product.stock} ${product.unit || 'পিস'})`
            : '❌ স্টক নেই';

        const caption =
            `🛍️ *${product.name}*\n` +
            `💰 মূল্য: ৳${Number(product.price).toLocaleString()}\n` +
            `${stockText}\n` +
            (product.description ? `\n📝 ${product.description}\n` : '') +
            `\nঅর্ডার করতে পরিমাণ লিখুন, যেমন:\n_"${product.name} ২টা চাই"_`;

        if (product.image_url) {
            // ছবি সহ পাঠাও
            try {
                const buffer = await fetchImageBuffer(product.image_url);
                await sock.sendMessage(jid, {
                    image:    buffer,
                    caption:  caption,
                    mimetype: 'image/jpeg',
                });
            } catch (imgErr) {
                // ছবি না পেলে শুধু text পাঠাও — flow বন্ধ হবে না
                console.warn('⚠️ Image fetch failed, sending text only:', imgErr.message);
                await sock.sendMessage(jid, { text: caption });
            }
        } else {
            // ছবি নেই — শুধু text
            await sock.sendMessage(jid, { text: caption });
        }

        console.log(`✅ Product card → ${phone}: ${product.name}`);
        res.json({ success: true });

    } catch (err) {
        console.error('❌ Product card error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ── QR Code ─────────────────────────────────────────────────
app.get('/qr', async (req, res) => {
    if (isConnected) return res.send(`<h2>✅ WhatsApp Connected!</h2>`);
    if (!currentQR)  return res.send(`<h2>⏳ QR এখনো তৈরি হয়নি। রিফ্রেশ করুন।</h2>`);
    try {
        const qrImage = await QRCode.toDataURL(currentQR);
        res.send(`
            <html><body style="text-align:center;font-family:sans-serif;padding:40px">
            <h2>📱 JIS-AI WhatsApp — QR Scan করুন</h2>
            <img src="${qrImage}" style="width:300px"/>
            <p>এই QR টি WhatsApp → Linked Devices থেকে scan করুন</p>
            <script>setTimeout(()=>location.reload(), 30000)</script>
            </body></html>`
        );
    } catch (err) {
        res.status(500).send('QR তৈরিতে সমস্যা');
    }
});

// ── Status & Health ─────────────────────────────────────────
app.get('/status', (req, res) => {
    res.json({ connected: isConnected, hasQR: !!currentQR, service: 'JIS-AI Baileys' });
});
app.get('/health', (req, res) => {
    res.json({ status: 'running ✅', connected: isConnected });
});

app.listen(PORT, () => {
    console.log(`🚀 Baileys Gateway চলছে → port ${PORT}`);
});
