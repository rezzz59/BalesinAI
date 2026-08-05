"""Industry blueprints — ready-made FAQ + catalog starter data per business_type.

Used during onboarding so a merchant doesn't start from an empty sheet:
  - BLUEPRINT_FAQS: generic questions+answers every store of that type should
    be able to answer. Used as a fallback knowledge source at lookup time.
  - BLUEPRINT_CATALOG_EXAMPLES: sample product rows to seed/illustrate a
    catalog (informational only — never used to answer buyer questions, so the
    bot can't invent prices).

FAQ answers here are deliberately generic (never brand/store specific) and are
meant to be customized by the merchant in their sheet.
"""

BLUEPRINT_FAQS: dict[str, list[dict[str, str]]] = {
    "jualan": [
        {"pertanyaan": "cara ordernya gimana?", "jawaban": "Untuk order, sebutkan produk yang diinginkan lalu kirim alamat pengiriman ya Kak."},
        {"pertanyaan": "pembayarannya bisa apa saja?", "jawaban": "Pembayaran bisa transfer bank atau e-wallet. Nanti kami kabari detail rekeningnya."},
        {"pertanyaan": "berapa lama pengirimannya?", "jawaban": "Pengiriman biasanya 1-3 hari kerja tergantung lokasi Kak."},
        {"pertanyaan": "apakah bisa retur?", "jawaban": "Bisa Kak, selama barang masih kondisi baik dan ada bukti video saat unboxing."},
    ],
    "kuliner": [
        {"pertanyaan": "jam buka sampai jam berapa?", "jawaban": "Kami buka setiap hari. Jam operasional bisa dicek di info profil ya Kak."},
        {"pertanyaan": "bisa delivery tidak?", "jawaban": "Bisa Kak, kami layani delivery dengan ongkir sesuai jarak."},
        {"pertanyaan": "bisa pesan untuk acara/katering?", "jawaban": "Bisa Kak, untuk pesanan banyak bisa hubungi kami dulu biar kami siapkan."},
        {"pertanyaan": "menu apa yang tersedia?", "jawaban": "Menu lengkapnya bisa dicek di katalog kami Kak. Sebutkan yang dicari ya."},
    ],
    "klinik": [
        {"pertanyaan": "jam buka kliniknya?", "jawaban": "Klinik buka sesuai jadwal yang tertera. Bisa cek jam operasional di info kami ya Kak."},
        {"pertanyaan": "cara daftar/konsultasi?", "jawaban": "Untuk konsultasi bisa langsung datang atau booking dulu lewat chat ini ya Kak."},
        {"pertanyaan": "berapa biaya konsultasi?", "jawaban": "Untuk biaya konsultasi bisa dikonfirmasi ke front office kami ya Kak."},
        {"pertanyaan": "apakah menerima BPJS?", "jawaban": "Mohon tanyakan ke front office untuk info BPJS dan layanan yang tersedia."},
    ],
    "fashion": [
        {"pertanyaan": "cara ordernya gimana?", "jawaban": "Untuk order, sebutkan produk, ukuran, dan alamat pengiriman ya Kak."},
        {"pertanyaan": "ukuran yang tersedia apa saja?", "jawaban": "Ukuran yang tersedia bisa dicek di katalog Kak, biasanya S sampai XL."},
        {"pertanyaan": "bisa tukar ukuran kalau salah?", "jawaban": "Bisa Kak, selama masih ada stok dan barang dalam kondisi baik."},
        {"pertanyaan": "bahan dan perawatannya?", "jawaban": "Detail bahan ada di deskripsi produk ya Kak."},
    ],
    "saas": [
        {"pertanyaan": "berapa harga paketnya?", "jawaban": "Kami punya 3 paket: Starter Rp149.000/bulan, Pro Rp399.000/bulan, dan Premium Rp899.000/bulan. Semua pakai free trial 14 hari tanpa kartu kredit."},
        {"pertanyaan": "paket mana yang cocok untuk saya?", "jawaban": "Starter cocok untuk toko kecil dengan chat sedikit, Pro untuk bisnis yang sudah ramai, dan Premium untuk yang butuh prioritas. Sebutkan skala bisnis Kakak biar kami bantu pilihkan."},
        {"pertanyaan": "ada free trial tidak?", "jawaban": "Ada Kak, free trial 14 hari dengan semua fitur Pro, tanpa kartu kredit."},
        {"pertanyaan": "apakah perlu bisa coding?", "jawaban": "Tidak perlu coding sama sekali Kak. Data dari Google Sheets dihubungkan, pilih jenis usaha, lalu selesai. Setup rata-rata 10 menit."},
        {"pertanyaan": "butuh nomor WhatsApp baru tidak?", "jawaban": "Tidak perlu Kak. Bot terhubung ke nomor WhatsApp yang sudah dipakai lewat gateway."},
        {"pertanyaan": "bagaimana cara mulai mencobanya?", "jawaban": "Klik tombol Coba Gratis, pilih paket, dan ikuti panduan di halaman daftar. Kami juga dampingi sampai bot aktif di WhatsApp Kakak."},
        {"pertanyaan": "apakah data pelanggan aman?", "jawaban": "Aman Kak. Data pelanggan dienkripsi dan hanya milik Kakak, tidak dibagikan ke pihak lain."},
        {"pertanyaan": "bisa batalkan langganan kapan saja?", "jawaban": "Bisa Kak, langganan bisa dibatalkan kapan saja tanpa penalti."},
        {"pertanyaan": "bagaimana cara membayar?", "jawaban": "Pembayaran bisa transfer bank atau e-wallet. Detail rekening dikirim setelah aktivasi."},
        {"pertanyaan": "apa saja fitur yang tersedia?", "jawaban": "Fitur utamanya: balas otomatis, pencatatan pesanan, deteksi keluhan, handoff ke owner, blueprint industri, dan dashboard inbox."},
        {"pertanyaan": "apakah bisa menangani komplain pelanggan?", "jawaban": "Bisa Kak. Sistem mendeteksi keluhan dan langsung memberi notifikasi ke Kakak agar cepat ditangani."},
        {"pertanyaan": "apakah cocok untuk jenis usaha saya?", "jawaban": "Blueprint sudah tersedia untuk jualan, kuliner, klinik, fashion, dan SaaS. Untuk jenis usaha lain, data tetap bisa dihubungkan dengan mudah."},
        {"pertanyaan": "apakah bisa upgrade paket?", "jawaban": "Bisa Kak, upgrade kapan saja dan selisihnya dihitung proporsional."},
        {"pertanyaan": "berapa lama proses aktivasi?", "jawaban": "Setelah data dihubungkan, bot bisa aktif dalam hitungan menit. Biasanya total setup tidak sampai 10 menit."},
        {"pertanyaan": "bagaimana kalau bot tidak tahu jawabannya?", "jawaban": "Bot tidak menebak-nebak Kak. Chat diserahkan ke owner lengkap dengan konteksnya, dan pelanggan diberi kabar."},
        {"pertanyaan": "apakah bisa integrasi dengan toko online?", "jawaban": "Bisa Kak. Data produk dari Google Sheets atau sistem yang Kakak punya bisa dihubungkan langsung."},
    ],
}

# Informational catalog samples — shown to the merchant as a starting point,
# never served to buyers as product data.
BLUEPRINT_CATALOG_EXAMPLES: dict[str, list[dict[str, str]]] = {
    "jualan": [
        {"nama_produk": "Produk Unggulan - Varian A", "harga": "50000", "ready": "Y", "deskripsi": "Contoh deskripsi produk. Ganti dengan produk asli Anda."},
        {"nama_produk": "Produk Unggulan - Varian B", "harga": "65000", "ready": "Y", "deskripsi": "Contoh deskripsi produk. Ganti dengan produk asli Anda."},
    ],
    "kuliner": [
        {"nama_produk": "Menu Andalan", "harga": "25000", "ready": "Y", "deskripsi": "Contoh menu utama. Ganti dengan menu asli Anda."},
        {"nama_produk": "Minuman Signature", "harga": "15000", "ready": "Y", "deskripsi": "Contoh minuman. Ganti dengan menu asli Anda."},
    ],
    "klinik": [
        {"nama_produk": "Layanan Konsultasi", "harga": "0", "ready": "Y", "deskripsi": "Contoh layanan. Ganti dengan layanan asli Anda."},
        {"nama_produk": "Paket Pemeriksaan", "harga": "0", "ready": "Y", "deskripsi": "Contoh paket. Ganti dengan layanan asli Anda."},
    ],
    "fashion": [
        {"nama_produk": "Koleksi Terbaru - Size S", "harga": "120000", "ready": "Y", "deskripsi": "Contoh produk fashion. Ganti dengan produk asli Anda."},
        {"nama_produk": "Koleksi Terbaru - Size M", "harga": "120000", "ready": "Y", "deskripsi": "Contoh produk fashion. Ganti dengan produk asli Anda."},
    ],
    "saas": [
        {"nama_produk": "Paket Starter", "harga": "149000", "ready": "Y", "deskripsi": "500 chat/bulan, balas otomatis, dukungan email."},
        {"nama_produk": "Paket Pro", "harga": "399000", "ready": "Y", "deskripsi": "5.000 chat/bulan, semua fitur Starter, dukungan 1-on-1."},
        {"nama_produk": "Paket Premium", "harga": "899000", "ready": "Y", "deskripsi": "Chat tanpa batas, semua fitur Pro, prioritas + konsultasi bulanan."},
    ],
}


def get_blueprint(business_type: str) -> dict:
    """Return the blueprint (faqs + catalog examples) for a business_type."""
    bt = (business_type or "jualan").strip().lower()
    return {
        "business_type": bt if bt in BLUEPRINT_FAQS else "jualan",
        "faqs": BLUEPRINT_FAQS.get(bt, BLUEPRINT_FAQS["jualan"]),
        "catalog_examples": BLUEPRINT_CATALOG_EXAMPLES.get(bt, BLUEPRINT_CATALOG_EXAMPLES["jualan"]),
    }


def available_business_types() -> list[str]:
    return sorted(BLUEPRINT_FAQS.keys())
