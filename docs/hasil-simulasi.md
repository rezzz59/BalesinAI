# Hasil Simulasi (Battery Test)

Berikut adalah hasil uji dry-run End-to-End dengan model Claude (via 9Router).

## Skenario Fashion

**1. Stok+ukuran+warna**
- pembeli : kak kemeja batik premiumnya ready size L warna navy ada ga?
- intent: check_product
- bot: Siap Kak, Kemeja Batik Pria Premium warna navy size L dengan bahan katun premium seharga Rp 135.000 saat ini ready siap kirim. 😊 Boleh dibantu nama dan alamat lengkap Kakak agar produknya bisa segera kami amankan?

**2. Tanya harga**
- pembeli : kak kemeja batiknya harganya berapa ya?
- intent: faq (terselesaikan via RAG hybrid catalog search)
- bot: Siap Kak! Kemeja Batik kami ready dengan ukuran M sampai XXL, bahan berkualitas dan motifnya elegan cocok untuk berbagai acara. Harganya Rp 135.000 per piece. Kakak mau ambil berapa piece dan pakai ukuran apa saja?

**3. Retur ukuran**
- pembeli : kak kalau salah ukuran bisa retur ga?
- intent: faq
- bot: Halo Kak, berikut info yang kami punya ya 😊 Bisa, retur ukuran dalam 3 hari dengan syarat belum dicuci dan tetap ada label toko.

**4. Beli 2 item**
- pembeli : mau beli 2 kaos oversize hitam kak
- intent: confirm_order
- bot: Baik Kak, untuk Kaos Oversize Cotton - Hitamnya. Biar kami bantu siapkan, boleh diisi format ini ya Kak:
Ukuran:
Warna:
Jumlah:

**5. Produk habis**
- pembeli : kak hoodie local brand ready ga?
- intent: check_product
- bot: Siap Kak, Hoodie Local Brand seharga Rp 180.000 dengan bahan fleece tebal saat ini sedang kosong. Kami bisa masukkan Kakak ke daftar tunggu untuk size M-XXL. Apakah Kakak bersedia kami hubungi kembali saat stoknya sudah ready?

## Skenario Katering

**7. Order lengkap**
- pembeli : kak mau pesan paket prasmanan a 100 porsi buat acara tanggal 12 juli, kirim ke jakarta barat, totalnya berapa ya?
- intent: confirm_order
- bot: Order diterima — total 100 porsi 🎉
  • Paket Prasmanan A x100 = Rp 3.500.000
  • Ongkir (jakarta barat): Rp 75.000
  Total: Rp 3.575.000 (DP 50%: Rp 1.787.500)
  Tanggal acara: 12 juli

**8. Order tanpa tanggal**
- pembeli : mau pesan paket prasmanan a 50 porsi, kirim ke jakarta selatan ya kak
- intent: confirm_order
- bot: Siap Kak! Untuk pesanannya, boleh dilengkapi dengan format ini ya:
Pesanan & Jumlah:
Tanggal Acara:
Alamat Pengiriman:

**10. Ongkir wilayah**
- pembeli : kak ongkir ke jakarta utara berapa ya?
- intent: faq
- bot: Halo Kak! 😊 Pengiriman ke Jakarta Utara bisa kami layani dengan ongkir sesuai jarak, namun tarif spesifiknya sedang kami konfirmasikan ke tim dahulu ya Kak. Boleh dibantu alamat lengkap pengirimannya agar kami bisa bantu hitungkan tarif tepatnya, Kak?

**11. Di bawah minimal**
- pembeli : ongkir 10 porsi nasi kotak ke tebet
- intent: faq (LLM context enforcement)
- bot: Siap Kak! Untuk rincian ongkos kirim ke Tebet, izinkan kami konfirmasi dulu dengan tim logistik ya Kak 🚚 Nanti kami kabari setelahnya. Sebelumnya perlu kami informasikan ya Kak, untuk Nasi Kotak Spesial minimal pemesanan 25 porsi. Apakah Kakak mau tambahkan porsinya agar cukup 25?

## Catatan Status
- **Semua skenario (termasuk S2 dan S11) telah terselesaikan.**
- Fallback sudah diatur menjadi natural dan human-like ("Wah, untuk pertanyaan ini kami pastikan dulu ya Kak...")
- Format pengisian pesanan disertakan otomatis saat user ingin membeli (meniru Cekat.AI format order prompt).
- Baterai test dan test runner pytest `345 tests` passed.
