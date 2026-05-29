// ============================================================
// JIS-AI — Baileys WhatsApp Gateway (আপডেট)
//
// নতুন কি যোগ হয়েছে:
//   ✅ /send-image   → ছবি + caption পাঠানো
//   ✅ /send-product  → পণ্যের ছবি ও বিবরণ একসাথে
//   ✅ /send-invoice  → Invoice HTML → PNG render → WhatsApp
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

// ── 4. Invoice PNG (Puppeteer render → WhatsApp image) ──────
// Body: { phone, invoice: { invoice_number, created_at, shop_name, owner_name,
//   sr_name, sr_code, items, replacement_items, total_amount, net_amount,
//   discount_amount, replacement_value, credit_balance_added,
//   payment_method, otp_verified } }

const buildInvoiceHTML = (invoice) => {
    const {
        invoice_number, created_at, shop_name, owner_name,
        sr_name, sr_code, items = [], replacement_items = [],
        total_amount, net_amount, discount_amount = 0,
        replacement_value = 0, credit_balance_added = 0,
        payment_method, otp_verified = false,
    } = invoice;

    const paymentLabels = { cash: '💵 নগদ', credit: '📋 বাকি', replacement: '↩️ রিপ্লেসমেন্ট' };
    const paymentColors = {
        cash:        { color: '#059669', bg: '#ecfdf5', border: '#059669' },
        credit:      { color: '#2563eb', bg: '#eff6ff', border: '#2563eb' },
        replacement: { color: '#d97706', bg: '#fffbeb', border: '#d97706' },
    };
    const pm = paymentColors[payment_method] || { color: '#6b7280', bg: '#f9fafb', border: '#6b7280' };

    const dateStr = new Date(created_at || Date.now())
        .toLocaleDateString('bn-BD', { day: 'numeric', month: 'long', year: 'numeric' });

    const itemsHTML = items.map(item => {
        const subtotal = parseFloat(item.qty) * parseFloat(item.price);
        return `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #f1f5f9;">
            <div>
                <p style="font-weight:600;color:#1f2937;font-size:14px;margin:0">${item.product_name}</p>
                <p style="color:#9ca3af;font-size:12px;margin:3px 0 0">${item.qty} × ৳${parseFloat(item.price).toLocaleString()}</p>
            </div>
            <p style="font-weight:700;color:#1f2937;font-size:14px;margin:0">৳${subtotal.toLocaleString()}</p>
        </div>`;
    }).join('');

    const replacementHTML = replacement_items.length > 0 ? `
        <div style="margin-top:12px;padding-top:12px;border-top:2px dashed #fed7aa;">
            <p style="font-size:11px;font-weight:700;color:#d97706;letter-spacing:1px;text-transform:uppercase;margin:0 0 8px">↩️ রিপ্লেসমেন্ট (ফেরত)</p>
            ${replacement_items.map(item => `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;">
                <div>
                    <p style="font-weight:600;color:#92400e;font-size:13px;margin:0">${item.product_name}</p>
                    <p style="color:#d97706;font-size:11px;margin:2px 0 0">${item.qty} পিস</p>
                </div>
                <p style="font-weight:700;color:#dc2626;font-size:13px;margin:0">-৳${parseFloat(item.total).toLocaleString()}</p>
            </div>`).join('')}
        </div>` : '';

    const discountRow = discount_amount > 0 ? `
        <div style="display:flex;justify-content:space-between;font-size:13px;background:#ecfdf5;border-radius:8px;padding:6px 10px;margin:3px 0;">
            <span style="font-weight:600;color:#059669">💳 ক্রেডিট ব্যালেন্স থেকে কাটা</span>
            <span style="font-weight:700;color:#059669">-৳${parseFloat(discount_amount).toLocaleString()}</span>
        </div>` : '';

    const replacementRow = replacement_value > 0 ? `
        <div style="display:flex;justify-content:space-between;font-size:13px;color:#d97706;padding:4px 0;">
            <span>রিপ্লেসমেন্ট বিয়োগ</span>
            <span style="font-weight:600">-৳${parseFloat(replacement_value).toLocaleString()}</span>
        </div>` : '';

    const creditAddedRow = credit_balance_added > 0 ? `
        <div style="display:flex;justify-content:space-between;font-size:13px;background:#ecfdf5;border-radius:8px;padding:6px 10px;margin:3px 0;">
            <span style="font-weight:600;color:#059669">✅ ব্যালেন্সে জমা হয়েছে</span>
            <span style="font-weight:700;color:#059669">+৳${parseFloat(credit_balance_added).toLocaleString()}</span>
        </div>` : '';

    return `<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>* { margin:0; padding:0; box-sizing:border-box; } body { font-family:'Hind Siliguri','Segoe UI',Arial,sans-serif; background:#e2e8f0; display:flex; justify-content:center; padding:20px; }</style>
</head>
<body>
<div style="background:#fff;border-radius:20px;overflow:hidden;width:400px;box-shadow:0 8px 40px rgba(0,0,0,0.18);font-family:'Hind Siliguri','Segoe UI',sans-serif;">

    <div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 60%,#1d4ed8 100%);padding:22px 24px 18px;position:relative;overflow:hidden;">
        <div style="position:absolute;top:-30px;right:-30px;width:130px;height:130px;border-radius:50%;background:rgba(255,255,255,0.06)"></div>
        <div style="position:absolute;bottom:-40px;left:-20px;width:110px;height:110px;border-radius:50%;background:rgba(255,255,255,0.04)"></div>
        <div style="display:flex;justify-content:space-between;align-items:flex-start;position:relative">
            <div>
                <p style="color:#fff;font-weight:800;font-size:18px;letter-spacing:-0.3px">NovaTech BD</p>
                <p style="color:rgba(255,255,255,0.5);font-size:11.5px;margin-top:3px">জানকি সিংহ রোড, বরিশাল</p>
            </div>
            <div style="text-align:right">
                <span style="background:rgba(255,255,255,0.12);color:rgba(255,255,255,0.65);font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;padding:3px 10px;border-radius:20px;display:block;margin-bottom:6px">INVOICE</span>
                <p style="color:#93c5fd;font-weight:700;font-size:12px;font-family:monospace">${invoice_number}</p>
            </div>
        </div>
        <div style="margin-top:16px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.1);display:flex;justify-content:space-between">
            <p style="color:rgba(255,255,255,0.45);font-size:11px">তারিখ</p>
            <p style="color:rgba(255,255,255,0.85);font-size:11.5px;font-weight:600">${dateStr}</p>
        </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;border-bottom:1.5px dashed #e5e7eb">
        <div style="padding:14px 18px;border-right:1.5px dashed #e5e7eb">
            <p style="font-size:10px;font-weight:700;color:#9ca3af;letter-spacing:1px;text-transform:uppercase;margin-bottom:5px">দোকান</p>
            <p style="font-weight:700;color:#111827;font-size:14px;line-height:1.3">${shop_name}</p>
            <p style="color:#6b7280;font-size:11.5px;margin-top:3px">${owner_name}</p>
        </div>
        <div style="padding:14px 18px">
            <p style="font-size:10px;font-weight:700;color:#9ca3af;letter-spacing:1px;text-transform:uppercase;margin-bottom:5px">SR</p>
            <p style="font-weight:700;color:#111827;font-size:14px;line-height:1.3">${sr_name || 'N/A'}</p>
            <p style="color:#6b7280;font-size:11.5px;margin-top:3px">${sr_code || ''}</p>
        </div>
    </div>

    <div style="padding:16px 18px">
        <div style="display:flex;justify-content:space-between;margin-bottom:10px">
            <p style="font-size:10px;font-weight:700;color:#9ca3af;letter-spacing:1px;text-transform:uppercase">পণ্য</p>
            <p style="font-size:10px;font-weight:700;color:#9ca3af;letter-spacing:1px;text-transform:uppercase">মূল্য</p>
        </div>
        ${itemsHTML}
        ${replacementHTML}
    </div>

    <div style="margin:0 18px 16px;border-radius:12px;background:#f8fafc;border:1px solid #e2e8f0;padding:12px 14px">
        <div style="display:flex;justify-content:space-between;font-size:13px;color:#4b5563;padding:4px 0">
            <span>পণ্যের মোট</span>
            <span style="font-weight:600">৳${parseFloat(total_amount || 0).toLocaleString()}</span>
        </div>
        ${discountRow}${replacementRow}${creditAddedRow}
        <div style="height:1px;background:#e2e8f0;margin:6px 0"></div>
        <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-weight:700;color:#0f172a;font-size:15px">পরিশোধযোগ্য</span>
            <span style="font-weight:800;color:#1e3a8a;font-size:20px">৳${parseFloat(net_amount || 0).toLocaleString()}</span>
        </div>
    </div>

    <div style="display:flex;justify-content:space-between;align-items:center;padding:0 18px 16px">
        <div style="display:inline-flex;align-items:center;gap:5px;background:${pm.bg};color:${pm.color};font-size:13px;font-weight:700;padding:5px 14px;border-radius:20px;border:1px solid ${pm.border}30">
            ${paymentLabels[payment_method] || payment_method}
        </div>
        <div style="display:flex;align-items:center;gap:5px;font-size:12px;font-weight:600">
            ${otp_verified ? '<span style="color:#059669">✅ OTP যাচাই ✓</span>' : '<span style="color:#9ca3af">❌ OTP অযাচাই</span>'}
        </div>
    </div>

    <div style="background:linear-gradient(135deg,#0f172a,#1e3a8a);padding:14px 18px;text-align:center">
        <p style="color:rgba(255,255,255,0.45);font-size:11px;letter-spacing:0.5px">আমাদের সাথে কেনাকাটার জন্য ধন্যবাদ 🙏</p>
        <p style="color:rgba(255,255,255,0.22);font-size:10px;margin-top:4px">NovaTech BD (Ltd.) • বরিশাল</p>
    </div>
</div>
</body>
</html>`;
};

app.post('/send-invoice', checkSecret, async (req, res) => {
    const { phone, invoice } = req.body;

    if (!phone || !invoice)
        return res.status(400).json({ error: 'phone এবং invoice data দিন' });
    if (!isConnected)
        return res.status(503).json({ error: 'WhatsApp connect হয়নি' });

    let browser = null;
    try {
        const jid       = formatJid(phone);
        const puppeteer = require('puppeteer');

        browser = await puppeteer.launch({
            headless: 'new',
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--font-render-hinting=none',
            ],
            executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
        });

        const page = await browser.newPage();
        await page.setViewport({ width: 460, height: 900, deviceScaleFactor: 2 });
        await page.setContent(buildInvoiceHTML(invoice), { waitUntil: 'networkidle0' });

        await page.waitForSelector('body > div');
        const element     = await page.$('body > div');
        const imageBuffer = await element.screenshot({ type: 'png', omitBackground: false });

        await browser.close();
        browser = null;

        const caption = `🧾 *${invoice.invoice_number}* | ${invoice.shop_name}\n💰 পরিশোধযোগ্য: *৳${parseFloat(invoice.net_amount || 0).toLocaleString()}*`;

        await sock.sendMessage(jid, {
            image:    imageBuffer,
            caption:  caption,
            mimetype: 'image/png',
        });

        console.log(`✅ Invoice Image → ${phone} (${invoice.invoice_number})`);
        res.json({ success: true, invoice_number: invoice.invoice_number });

    } catch (err) {
        if (browser) { try { await browser.close(); } catch (_) {} }
        console.error('❌ Invoice send error:', err.message);
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
