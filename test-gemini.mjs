import https from 'node:https';

const activeApiKey = process.env.GEMINI_API_KEY || '';
if (!activeApiKey) {
  console.log("No API key");
  process.exit(1);
}

const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=' + activeApiKey;

const data = JSON.stringify({
  contents: [{ parts: [{ text: "Hello" }] }],
  systemInstruction: { parts: [{ text: "You are a helpful assistant." }] }
});

const req = https.request(url, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(data)
  }
}, (res) => {
  let str = '';
  res.on('data', (c) => str += c);
  res.on('end', () => {
    console.log("Status:", res.statusCode);
    console.log("Response:", str);
  });
});

req.on('error', (e) => console.error(e));
req.write(data);
req.end();
