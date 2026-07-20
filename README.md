# Günlük Endüstriyel Otomasyon Proje Fabrikası

Her gün öğrenciler ve otomasyona yeni başlayanlar için küçük, anlaşılır ve
simülasyonla denenebilir bir endüstriyel otomasyon projesi üreten GitHub yayın
sistemi. Ana odak Beckhoff TwinCAT 3, PLC, IEC 61131-3 Structured Text ve
Python tabanlı eğitim simülasyonlarıdır.

Bu depo üç işi otomatikleştirir:

1. `config/project_ideas.json` içinden günün PLC/otomasyon fikrini seçer.
2. OpenAI Responses API ile güvenli sınırlar içinde Türkçe anlatımlı bir
   TwinCAT Structured Text projesi ve Python simülasyonu üretir.
3. Projeyi yeni bir GitHub deposunda yayımlar; profil README'sindeki
   **Son Projeler** alanını günceller.

## Neden böyle tasarlandı?

- Her eğitim projesi ayrı bir depoda yayımlanır.
- Üretilen dosyalara yol, boyut, uzantı ve Python sözdizimi kontrolleri uygulanır.
- PLC kodunda doğrudan donanım adreslemesi kullanılmaz; sembolik I/O tercih edilir.
- Model çıktısı yayınlanmadan önce tehlikeli kod kalıpları için taranır.
- Zamanlanmış yayın, depo değişkeni açılana kadar kapalıdır.
- Aynı gün yeniden çalıştırılırsa ikinci bir depo oluşturmaz.
- OpenAI ve GitHub anahtarları yalnızca GitHub Secrets içinde tutulur.

## Hızlı başlangıç

Yerel ve anahtarsız bir prova:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/publish_daily.py --dry-run --date 2026-07-20
```

Çıktı `build/` altında oluşur ve hiçbir yere gönderilmez.

Gerçek yayın için [kurulum rehberini](docs/SETUP.md) izleyin. İlk hazır proje
örneği [`starter-project/`](starter-project/) klasöründedir.

## Günlük ritim

İş akışı varsayılan olarak her gün `09:15 Europe/Istanbul` saatinde tetiklenir.
GitHub zamanlanmış iş akışlarında birkaç dakikalık gecikme olabilir.

## Maliyet kontrolü

Varsayılan model `gpt-5.6-luna` ve çıktı limiti 12.000 tokendir. Model,
`OPENAI_MODEL` depo değişkeniyle değiştirilebilir. Her yayın bir API çağrısı
yapar; gerçek maliyet seçilen modele ve üretilen çıktı uzunluğuna bağlıdır.

## Güvenlik notu

Bu sistem model tarafından oluşturulan PLC kodunu gerçek cihaza yüklemez.
Python dosyalarını AST ile ayrıştırır, riskli kalıpları tarar ve yalnızca izin
verilen dosya türlerini yayımlar. Tüm örnekler eğitim ve simülasyon amaçlıdır.
Gerçek makine, proses veya emniyet uygulamasında kullanılmadan önce yetkin bir
otomasyon uzmanı tarafından risk analizi, donanım doğrulaması ve saha testi
yapılması gerekir. Standart PLC kodu, sertifikalı emniyet fonksiyonunun yerine
geçmez.

## Lisans

MIT
