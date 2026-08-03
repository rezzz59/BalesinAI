# Deploy ke Vercel

## Frontend (Web Tester)

### Langkah 1: Push ke GitHub
```bash
git add .
git commit -m "Add web tester frontend"
git push origin main
```

### Langkah 2: Deploy ke Vercel
```bash
npm install -g vercel
vercel --prod
```

Atau gunakan CLI:
```bash
npx vercel
```

### Langkah 3: Konfigurasi API URL
Setelah deploy, buka web tester dan atur:
- **API Base URL**: `https://your-backend.onrender.com` atau URL backend Anda

## Backend (Python/FastAPI)

Backend perlu di-host di layanan yang support Python:

### Opsi 1: Render (Gratis)
1. Push repo ke GitHub
2. Buka https://render.com
3. Buat New Web Service
4. Pilih repo Anda
5. Set Build Command: `pip install -r requirements.txt`
6. Set Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
7. Deploy

### Opsi 2: Railway
1. Push repo ke GitHub
2. Buka https://railway.app
3. New Project → Deploy from GitHub repo
4. Set environment variables:
   - `LLM_BACKEND=gemini`
   - `GEMINI_API_KEY=your_key`
   - `ENCRYPTION_KEY=your_key`
5. Deploy

## Struktur File
```
├── frontend/
│   └── index.html      # Web tester UI
├── app/
│   └── main.py         # FastAPI backend
├── vercel.json         # Vercel config
└── DEPLOY_VERCEL.md    # Instruksi deploy
```
