#!/usr/bin/env python3
"""Generate realistic mid-size Indonesian e-commerce stress-test fixtures.

Outputs:
  fixtures/sample_faq_katalog.xlsx — 50 FAQ rows + 500 Katalog products
  fixtures/sample_customer_questions.txt — 30 natural-language questions
  fixtures/expected_template_responses.txt — same questions answered by a
    static template bot (for side-by-side comparison demo)

Sheet schema matches what app/services/sheets.py expects:
  FAQ: pertanyaan, jawaban
  Katalog: nama_produk, harga, ready, deskripsi

Idempotent: re-running overwrites the output files.

Usage:
  python scripts/gen_stress_fixtures.py
"""
import os
import random
from openpyxl import Workbook

random.seed(42)  # deterministic

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "fixtures")
os.makedirs(FIXTURES, exist_ok=True)

# ---------------------------------------------------------------------------
# FAQ: 50 realistic customer questions for an Indonesian clothing store.
# ---------------------------------------------------------------------------
FAQ = [
    ("Berapa harga kaos polos?", "Mulai Rp 50.000 untuk Cotton Combed 24s, Rp 75.000 untuk Oversize Boxy."),
    ("Apa saja warna yang tersedia?", "Hitam, Putih, Navy, Merah Maroon, Abu Misty, Sage Green, dan Dusty Pink."),
    ("Berapa lama pengiriman?", "2-4 hari kerja untuk Jabodetabek, 5-7 hari luar kota, 7-14 hari ke Indonesia timur."),
    ("Apakah bisa COD?", "Bisa untuk area Jabodetabek dan Bandung. Di luar itu harus transfer dulu."),
    ("Bagaimana cara pembayaran?", "Transfer BCA/Mandiri/BNI, QRIS, GoPay, OVO, Dana, ShopeePay."),
    ("Apakah ada diskon untuk grosir?", "Ada. Minimal 50 pcs dapat harga khusus, hubungi WA admin untuk quotation."),
    ("Bahan kaos apa yang paling adem?", "Cotton Combed 24s paling adem, Bamboo Cotton paling premium (Rp 95.000)."),
    ("Ukuran kaosnya gimana?", "S (lingkar dada 96cm), M (100cm), L (104cm), XL (110cm), XXL (118cm). Toleransi ±2cm."),
    ("Bisa custom sablon tidak?", "Bisa, minimal 24 pcs per desain. biaya sablon Rp 15.000/pcs warna, Rp 25.000/pcs untuk DTF."),
    ("Berapa minimal order?", "Ecer 1 pcs boleh. Untuk custom sablon minimal 24 pcs."),
    ("Stok ready apa saja?", "Semua kaos polos, hoodie, dan topi ready. Crewneck Basic pre-order 7 hari."),
    ("Ada hoodie tidak?", "Ada, Hoodie Fleece Tebal Rp 150.000, bahan fleece 380gsm, ready stock hitam dan abu."),
    ("Topi snapback masih ada?", "Ready, Rp 65.000, adjustable, one size fits all."),
    ("Bisa kirim ke luar negeri?", "Bisa ke Malaysia dan Singapura via JNE Yes atau SiCepat. Ongkir ditanggung pembeli."),
    ("Apakah ada garansi?", "Garansi tukar baru jika ada cacat produksi dalam 7 hari setelah diterima."),
    ("Bahan hoodie tebal tidak?", "Fleece 380gsm, tebal, hangat. Cocok untuk AC dan dingin."),
    ("Kaos oversize panjangnya sampai mana?", "Panjang body 72cm, panjang tangan 24cm dari pundak untuk size L."),
    ("Warna sage green ready?", "Ready di Cotton Combed 24s size M dan L saja."),
    ("Bisa retur kalau salah ukuran?", "Bisa tukar size asal belum dicuci dan tag masih ada. Ongkir retur ditanggung pembeli."),
    ("Ada katalog PDF?", "Belum ada, tapi bisa langsung lihat di katalog WhatsApp ini atau Instagram @kaosjakarta."),
    ("Bagaimana cara ordernya?", "Ketik produk yang dicari, misal 'kaos hitam oversize', nanti saya bantu carikan dan konfirmasi pesanan."),
    ("Ongkir ke Surabaya berapa?", "SiCepat REG sekitar Rp 18.000-25.000 untuk 1 kg, JNE YES 1-2 hari Rp 35.000."),
    ("Ada diskon hari ini?", "Lihat promo berjalan di Instagram @kaosjakarta. Untuk 5 pcs ke atas gratis ongkir Jabodetabek."),
    ("Bisa pakai ShopeePay?", "Bisa, transfer ke nomor ShopeePay nanti kami kirim setelah konfirmasi pesanan."),
    ("Bahan Cotton Combed 24s artinya apa?", "Berarti cotton dengan ketebalan benang 24s, lebih tipis dan adem dari 20s."),
    ("Kapan pesanan saya diproses?", "Sebelum jam 14.00 diproses hari ini, setelahnya besok pagi. Resi keluar setelahnya."),
    ("Resi dikirim bagaimana?", "Otomatis via WhatsApp ke nomor yang order begitu paket di-pickup kurir."),
    ("Bisa ambil di toko?", "Bisa, alamat toko: Jl. Tebet Barat Dalam IV No.12, Jakarta Selatan. Buka 10.00-19.00."),
    ("Apakah kainnya menyusut setelah dicuci?", "Susut max 5% untuk cotton combed, karena sudah pre-shrunk. Cuci dingin dan jangan pakai pengering."),
    ("Ada size chart untuk wanita?", "Kaos oversize unisex. Untuk wanita size S atau M biasanya cukup."),
    ("Bisa order lewat Tokopedia juga?", "Bisa, tapi harga di Tokopedia lebih tinggi karena ada fee platform. Lewat sini lebih murah."),
    ("Berapa harga grosir 100 pcs?", "Kaos polos Rp 35.000/pcs untuk 100 pcs. Hubungi admin untuk detail."),
    ("Bisa DP 50%?", "Bisa untuk order di atas Rp 1.000.000, pelunasan sebelum pengiriman."),
    ("Kaos hitamnya ada yang glossy?", "Tidak, semua hitam matte. Untuk glossy ada di bahan Dry Fit Rp 65.000."),
    ("Dry Fit untuk olahraga?", "Ya, cocok untuk lari dan gym, cepat kering."),
    ("Bisa pesan warna custom?", "Untuk 100 pcs ke atas bisa request warna Pantone."),
    ("Ada reward untuk repeat order?", "Setiap 10x order dapat diskon 10% atau free ongkir berikutnya."),
    ("Bagaimana kualitas sablonnya?", "Plastisol import, tahan 50+ kali cuci tanpa retak."),
    ("Sablon DTF itu apa?", "Direct to Film, full color, cocok untuk desain banyak warna. Lebih fleksibel dari plastisol."),
    ("Bisa pakai desain sendiri?", "Bisa, kirim file AI/PNG/CDR resolusi tinggi, biaya desain Rp 50.000 jika belum ada."),
    ("Lead time custom sablon?", "7-14 hari kerja setelah desain disetujui dan DP masuk."),
    ("Bahan apa yang paling laris?", "Cotton Combed 24s warna hitam dan putih."),
    ("Ada size XXXL?", "Tidak ada di ready stock, tapi bisa pre-order 10 hari untuk XXXL Cotton Combed."),
    ("Bagaimana cara komplain?", "Kirim pesan 'komplain [nomor order] [masalah]', nanti saya sambungkan ke admin."),
    ("Apakah ada program reseller?", "Ada, daftar lewat admin dengan minimal order pertama 50 pcs."),
    ("Bisa pakai payment credit?", "Tidak, semua pembayaran cash/transfer di muka."),
    ("Warna merah maroon ready size XL?", "Ready di Cotton Combed 24s dan Oversize Boxy."),
    ("Bahan fleece itu hangat?", "Sangat hangat, cocok untuk AC kantor dan dingin."),
    ("Bisa order dari Kalimantan?", "Bisa, biasanya pakai JNE atau SiCepat, sampai 5-7 hari."),
    ("Bagaimana tracking resi?", "Saya kirim nomor resi otomatis, tinggal cek di website JNE/SiCepat."),
    ("Ada warna baby blue?", "Untuk sementara ganti Sage Green, baby blue pre-order 14 hari."),
]

# ---------------------------------------------------------------------------
# Katalog: 500 products. Templates generate realistic Indonesian clothing names.
# ---------------------------------------------------------------------------
PRODUCT_TYPES = [
    ("Kaos Polos Cotton Combed 24s", 50000, "Y", "100% katun, adem, adem dipakai sehari-hari"),
    ("Kaos Polos Cotton Combed 20s", 60000, "Y", "Lebih tebal dari 24s, lebih tahan lama"),
    ("Kaos Oversize Boxy", 75000, "Y", "Cutting boxy, bahan tebal premium, streetwear style"),
    ("Kaos Oversize Crop", 70000, "Y", "Potongan crop di wanita, unisex untuk pria size S"),
    ("Hoodie Fleece Tebal", 150000, "Y", "Bahan fleece 380gsm, hangat untuk AC dan dingin"),
    ("Hoodie Basic Cotton", 130000, "N", "100% cotton, ringan, pre-order 7 hari"),
    ("Crewneck Basic", 120000, "N", "Tanpa hoodie, casual, pre-order 7 hari"),
    ("Crewneck Heavyweight", 175000, "N", "500gsm, premium, pre-order 10 hari"),
    ("Topi Snapback", 65000, "Y", "Adjustable, one size fits all, bahan premium"),
    ("Topi Trucker", 55000, "Y", "Jaring di belakang, cocok untuk olahraga outdoor"),
    ("Topi Beanie", 45000, "Y", "Rajut, untuk dingin, one size"),
    ("Kaos Dry Fit Polos", 65000, "Y", "Cepat kering, cocok olahraga, anti-bau"),
    ("Kaos Dry Fit Motif", 85000, "Y", "Sublim, full color, untuk lari dan gym"),
    ("Polo Shirt Cotton", 95000, "Y", "Kerja casual, ada kancing, cotton pique"),
    ("Polo Shirt Dry Fit", 110000, "Y", "Untuk lapangan dan olahraga, anti-kusut"),
    ("Kemeja Flannel Kotak-Kotak", 125000, "Y", "Bahan flannel tebal, cocok untuk dingin"),
    ("Kemeja Denim Casual", 135000, "N", "Denim ringan, pre-order 5 hari"),
    ("Jogger Pants Cotton", 145000, "Y", "Celana training, ada kantong, elastic pinggang"),
    ("Celana Chino Slim", 165000, "N", "Bahan chino, formal casual, pre-order 5 hari"),
    ("Sweater Rajut", 155000, "N", "Rajut tangan, premium, pre-order 14 hari"),
]

WARNA = [
    "Hitam", "Putih", "Navy", "Merah Maroon", "Abu Misty",
    "Sage Green", "Dusty Pink", "Cream", "Olive", "Mustard",
    "Coklat Muda", "Biru Muda", "Hijau Botol", "Merah Cabe",
]
SIZES = ["S", "M", "L", "XL", "XXL"]

def generate_catalog():
    """Build 500 catalog rows by combining product types, colors, sizes."""
    rows = []
    for i in range(500):
        prod = random.choice(PRODUCT_TYPES)
        nama, harga, ready, desc = prod
        warna = random.choice(WARNA)
        size = random.choice(SIZES)
        # Vary price ±20% for color/size combos
        variance = random.choice([0, 0, 0, 0, 5000, -5000, 10000])
        final_price = max(20000, harga + variance)
        full_name = f"{nama} - {warna} - Size {size}"
        full_desc = f"{desc}. Varian warna {warna}, size {size}."
        rows.append({
            "nama_produk": full_name,
            "harga": final_price,
            "ready": ready,
            "deskripsi": full_desc,
        })
    return rows

# ---------------------------------------------------------------------------
# Customer questions: 30 natural-language messages a real buyer might send.
# Mix of FAQ-style, product-search, ambiguous, slang, multi-intent, off-topic.
# ---------------------------------------------------------------------------
CUSTOMER_QUESTIONS = """\
berapa sih harga kaos hitam yang paling murah?
kaos oversize warna sage ready ga?
bisa kirim ke bandung hari ini juga ga?
aku cari hoodie yang bahan tebal, ada rekomendasi?
bayar pake gopay bisa ga?
ongkir ke surabaya berapa ya kira2?
kaos oversize size L warnanya navy ready?
kaos cotton combed warna baby blue ada?
kalo beli 5 pcs bisa gratis ongkir ga?
kaos putih size M ready?
hoodie hitam ready semua size ga?
kaos oversize boxy itu panjangnya berapa cm?
bisa custom sablon ga? minimal order berapa?
ini beneran ada admin nya atau cuma bot?
kak, mau tanya warna merah cabe ready size XL ga?
kaos oversize buat wanita size apa yg pas?
pembayaran pake shopepay bisa kan?
kirim ke kalimantan bisa ga kak?
ada size XXXL ga?
jaket hoodie nya anti bau ga?
kaos oversize cotton combed 20s ada warna sage?
mau jadi reseller, syaratnya apa?
gimana cara komplain kalau barang rusak?
sablon DTF itu awet ga kalau dicuci?
kaosnya bisa dicuci pake mesin ga?
kak, topi snapback warna olive ready?
bisa retur kalau kekecilan?
kain fleece nya tebal brp gram?
ongkirnya murahin dong, lagi promo kan?
kaos oversize yang boxy aja deh, ready ga?\n"""

# ---------------------------------------------------------------------------
# Template bot responses: same questions answered by a fixed-menu bot that
# can't understand context, has no catalog awareness, uses canned answers.
# Demonstrates where AI-agent beats templates.
# ---------------------------------------------------------------------------
TEMPLATE_RESPONSES = """\
SELAMAT DATANG DI TOKO KAMI. Ketik 1 untuk daftar harga, 2 untuk warna, 3 untuk ongkir.
[NO MATCH]
[NO MATCH]
[NO MATCH]
Untuk custom sablon hubungi admin di jam kerja.
[NO MATCH]
[NO MATCH]
[NO MATCH]
[NO MATCH]
Ketik 1 untuk kaos, 2 untuk hoodie, 3 untuk topi.
[NO MATCH]
[NO MATCH]
Hubungi admin untuk pertanyaan spesifik.
[NO MATCH]
[NO MATCH]
[NO MATCH]
Ketik HELP untuk bantuan.
[NO MATCH]
[NO MATCH]
[NO MATCH]
Ketik HELP untuk bantuan.
[NO MATCH]
[NO MATCH]
[NO MATCH]
Ketik 1 untuk kaos, 2 untuk hoodie, 3 untuk topi.
[NO MATCH]
[NO MATCH]
[NO MATCH]
[NO MATCH]
[NO MATCH]
Hubungi admin untuk pertanyaan spesifik.\n"""

# ---------------------------------------------------------------------------
# Generate files
# ---------------------------------------------------------------------------
def write_xlsx(path, faq_rows, catalog_rows):
    wb = Workbook()
    faq_ws = wb.active
    faq_ws.title = "FAQ"
    faq_ws.append(["pertanyaan", "jawaban"])
    for q, a in faq_rows:
        faq_ws.append([q, a])
    cat_ws = wb.create_sheet("Katalog")
    cat_ws.append(["nama_produk", "harga", "ready", "deskripsi"])
    for row in catalog_rows:
        cat_ws.append([row["nama_produk"], row["harga"], row["ready"], row["deskripsi"]])
    wb.save(path)

def main():
    print(f"Generating {len(FAQ)} FAQ rows + {500} catalog rows...")
    catalog = generate_catalog()
    write_xlsx(
        os.path.join(FIXTURES, "sample_faq_katalog.xlsx"),
        FAQ, catalog,
    )
    with open(os.path.join(FIXTURES, "sample_customer_questions.txt"), "w") as f:
        f.write(CUSTOMER_QUESTIONS)
    with open(os.path.join(FIXTURES, "expected_template_responses.txt"), "w") as f:
        f.write(TEMPLATE_RESPONSES)
    print(f"Wrote fixtures to {FIXTURES}/")
    print("Files:")
    for name in ("sample_faq_katalog.xlsx", "sample_customer_questions.txt", "expected_template_responses.txt"):
        path = os.path.join(FIXTURES, name)
        size = os.path.getsize(path)
        print(f"  {name} ({size:,} bytes)")

if __name__ == "__main__":
    main()