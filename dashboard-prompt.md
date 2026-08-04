# Prompt: Dashboard Merchant "OrderCloser" (Produksi, Bukan Template AI)

## Peran & Tujuan
Kamu adalah product designer + frontend engineer senior. Bangun satu halaman **Dashboard Merchant** untuk produk chatbot WA penjualan UMKM Indonesia bernama **OrderCloser**. Dashboard ini dilihat pemilik toko kecil (bukan developer) di HP dan laptop. Tujuan: pemilik tahu **berapa order masuk, berapa uang masuk, apakah botnya sehat, dan apa yang butuh tindakan**. Hasilnya harus tampak seperti produk startup Indonesia yang benar-benar diluncurkan — bukan hasil generate AI.

## Larangan Keras (Tanda AI)
- **TANPA** gradient ungu/biru futuristik, tanpa warna neon, tanpa glow/glassmorphism.
- **TANPA** emoji berlebihan. Maksimal 1 ikon hati-hati; lebih baik pakai ikon SVG.
- **TANPA** teks "Lorem ipsum", "dashboard Anda", "di sini", atau placeholder kaku.
- **TANPA** kopian robotik seperti "Selamat datang! Nikmati fitur kami". Bahasa harus seperti pemilik toko sungguhan bicara.
- **TANPA** angka acak yang tidak masuk akal (harga gorengan Rp 4.700.000). Semua data contoh harus realistis untuk UMKM Indonesia.
- **TANPA** layout simetris kaku hasil template. Beri variasi tinggi card, kepadatan, dan hierarki.
- Tidak semua isi halaman harus muat di satu layar — buat padat tapi tidak sesak, beri napas.

## Arah Visual (Art Direction)
- Palet: netral hangat (putih, abu muda `#F8F7F4`, abu teks `#4A4A45`), aksen **hijau toska/emerald** `#0E9F6E` sebagai warna utama brand, **amber** `#B7791F` untuk peringatan, **merah** `#C53030` untuk error/urgent. TIDAK ada warna ungu/biru tua.
- Tipografi: **Plus Jakarta Sans** (pakai Google Fonts) untuk semuanya, angka pakai `font-variant-numeric: tabular-nums`. Ukuran: judul 20px bold, kartu angka 28px bold, label 12px, teks badan 14px.
- Sudut card 12px, bayangan halus `0 1px 2px rgba(0,0,0,.05), 0 4px 12px rgba(0,0,0,.04)`. Garis pemisah 1px abu sangat muda.
- Ikon: satu set SVG garis (stroke 1.5) konsisten — pakai Lucide. Jangan campur library ikon.
- Grafik: garis halus, tidak mencolok. Label sumbu ringkas ("Sen", "Sel", "Rab"). Tooltip minimal.
- Background: abu netral hangat `#F8F7F4`, card putih.

## Layout
- **Sidebar kiri** (lebar ~220px, collapse di mobile): logo + nama "OrderCloser", menu: Ringkasan, Pesanan, Percakapan, Katalog, Pengaturan. Aktifkan "Ringkasan". Di bawah: kartu kecil "Koneksi WA aktif" + nomor bot.
- **Header** (perluas konten): nama toko "Warung Kopi Nusantara", badge "Paket Pro", tombol "Tambah Produk" dan avatar pemilik.
- Body = halaman Ringkasan dengan blok di bawah.

## Blok Konten (Ringkasan) — Pakai data contoh realistis

### 1. Baris Kartu KPI (4 kartu, tidak seragam — satu kartu boleh lebih tinggi)
- **Pesanan Hari Ini**: angka besar `12`, subtitle `+3 dari kemarin`, garis tren kecil (sparkline).
- **Pendapatan Hari Ini**: `Rp 845.000`, subtitle `Omzet: Rp 4,2 jt minggu ini`.
- **Dibalas Bot**: `78%` dengan mini progress bar, subtitle `22 pesan dialihkan ke owner` (kartu ini diberi aksen amber karena ada yang perlu perhatian).
- **Butuh Tindakan**: `5` dalam teks merah, subtitle `pesanan pending & pertanyaan belum terjawab`. Kartu ini paling kecil.

### 2. Grafik Utama: Pendapatan 7 Hari
Bar chart 7 hari (Sen–Ming), tinggi konsisten. Beberapa hari menonjol (mis. Jum Rp 1,1 jt), weekend lebih sepi. Ada toggle kecil "7 hari / 30 hari" (yang aktif "7 hari"). Di atasnya: total `Rp 5,8 jt` + `+12% dari minggu lalu`. Tooltip: `Jumat · 24 Okt` → `Rp 1.150.000 · 16 pesanan`.

### 3. Dua Kolom: Pesanan Terbaru + Bot Health
Kiri (lebih lebar) **Pesanan Terbaru** — tabel 5 baris, kolom: Kode (`#OC-4821`), Pelanggan (nama asli Indonesia: "Budi Santoso", "Rina Wulandari"), Produk ("Kopi Susu x2 · Es Teh x1"), Total (`Rp 42.000`), Status (badge berwarna: Dipesan=amber, Dikonfirmasi=biru muda, Dibayar=hijau, Selesai=hijau tua, Batal=abu/merah), Waktu ("10:24"). Kolom tindakan: titik tiga untuk menu. Footer: tombol teks "Lihat semua pesanan →".

Kanan **Kesehatan Bot** — daftar 4 metrik dengan angka + konteks:
- Pertanyaan dijawab otomatis: `78%` → "5 dari 23 pesan butuh owner"
- Waktu balas rata-rata: `< 1 menit`
- Skor kesiapan bot: `85/100` (bar tipis)
- Pertanyaan belum ada jawabannya: `3` → daftar: "jam buka hari libur?", "bisa kredit?", "harga borongan" (tautan "Tambah jawaban").

### 4. Dua Kolom Kedua: Aktivitas Owner + Produk Terlaris
Kiri **Aktivitas & Notifikasi** — feed vertikal 4 item dengan ikon kecil:
- `10:24` — Pesanan baru #OC-4821, Budi Santoso
- `10:02` — Komplain dialihkan: "pesanan belum sampai 3 hari"
- `09:40` — Jawaban baru ditambahkan: "ongkir ke Bali"
- `09:12` — Bot uji: skor naik 78 → 85

Kanan **Produk Terlaris** — 4 baris: nama produk, jumlah terjual, mini bar proporsi relatif terhadap terlaris. ("Kopi Susu — 24 · Es Teh — 19 · Roti Bakar — 12 · Pisang Goreng — 9").

## Microcopy & Bahasa
- Bahasa Indonesia santai tapi profesional. Sapaan natural, bukan kaku. Contoh judul blok: "Pesanan Terbaru", "Kesehatan Bot", "Perlu Perhatian".
- Tooltip/empty state harus membantu, bukan robotik. Contoh empty state: "Belum ada pesanan masuk. Share nomor WA bot ke pelanggan ya — order akan muncul di sini."
- Angka pakai format Rupiah: `Rp 845.000`, ribuan dengan titik.

## Interaksi & State (wajib)
- **Hover**: row tabel mengambang abu halus; kartu KPI sedikit terangkat; tombol punya state hover.
- **Empty state**: blok "Percakapan" kosong menampilkan ilustrasi SVG sederhana (bukan emoji) + pesan ramah.
- **Loading**: skeleton abu berdenyut halus per blok (bukan spinner besar).
- **Responsive**: di layar <768px, KPI jadi 2 kolom, dua-kolom jadi tumpuk, sidebar jadi ikon saja + menu hamburger.

## Struktur Teknis
- Satu file `index.html` mandiri: CSS inline dalam `<style>` + JS ringan dalam `<script>`, atau split rapi (CSS/JS eksternal lokal).
- Data contoh dideklarasikan sebagai array JS `const ORDERS = [...]` agar mudah diganti API nanti. Tandai komentar `// API`.
- Grafik bar buat manual dengan div/percent, JANGAN pakai library chart berat — cukup dependency ringan atau vanilla.
- Font: Google Fonts Plus Jakarta Sans.
- Aksesibilitas: kontras cukup, label aria pada ikon tombol, fokus terlihat.

## Pengukuran "Berhasil"
Halaman terlihat seperti dashboard produk fintech/e-commerce Indonesia sungguhan (misal nuansa GoBiz / Moka / Digipos). Orang pertama yang lihat TIDAK berkata "ini dibuat AI". KOPIAN, DATA, dan hierarki visual yang paling membedakan.
