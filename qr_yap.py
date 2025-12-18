import qrcode

# Senin Render adresin (Herkesin gireceği link)
url = "https://inegol-gastro-menu.onrender.com"

# QR Kodu Oluştur
qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_H, # Hata düzeltme yüksek (Logolu basarsan bozulmasın diye)
    box_size=10,
    border=4,
)

qr.add_data(url)
qr.make(fit=True)

# Renk Ayarları (Marka rengin Turuncu ve Koyu Lacivert)
img = qr.make_image(fill_color="#ea580c", back_color="white") # Turuncu QR

# Kaydet
img.save("gastro_qr_hd.png")
print("✅ QR Kod başarıyla oluşturuldu: gastro_qr_hd.png")