# Kurulum

Kurulum iki GitHub deposu kullanır:

- `zafercetinautomation/zafercetinautomation`: GitHub profil README deposu
- `zafercetinautomation/daily-automation-factory`: Bu otomasyonun kaynak deposu

## 1. Profil deposu

`zafercetinautomation` adında herkese açık bir depo oluşturun. Bu depodaki
`profile/README.md` dosyasını yeni deponun kökündeki `README.md` olarak
kopyalayın.

## 2. Yayıncı deposu

Bu klasörü `daily-automation-factory` adlı herkese açık bir depoya gönderin.

## 3. GitHub erişim anahtarı

GitHub'da fine-grained personal access token oluşturun:

- Repository access: **All repositories**
- Repository permissions / Administration: **Read and write**
- Repository permissions / Contents: **Read and write**

Anahtarı `daily-automation-factory` deposunda:

`Settings → Secrets and variables → Actions → Secrets`

altında `GH_PROFILE_TOKEN` adıyla kaydedin. Bu anahtar yeni depo oluşturmak,
dosyalarını yayımlamak ve profil README'sini güncellemek için kullanılır.

Anahtarı hiçbir zaman `.env`, kod, issue veya log içine yapıştırmayın.

## 4. OpenAI anahtarı

OpenAI API anahtarını aynı Secrets ekranına `OPENAI_API_KEY` adıyla ekleyin.
ChatGPT aboneliği ile API kullanımı aynı faturalandırma sistemi değildir; API
kullanımı ayrıca ücretlendirilir.

## 5. Önce prova

`Actions → Publish daily AI project → Run workflow` ekranında:

- `publish`: kapalı
- `date`: boş

çalıştırın. Oluşan `daily-ai-dry-run` artifact'ını inceleyin.

## 6. İlk gerçek yayın

Aynı iş akışını `publish` açık olarak bir kez çalıştırın. Yeni proje deposu ve
profilin **Son projeler** bölümü oluştuğunda otomasyon hazırdır.

## 7. Günlük yayını açma

`Settings → Secrets and variables → Actions → Variables` altında:

- `DAILY_PUBLISH_ENABLED` = `true`
- İsteğe bağlı `OPENAI_MODEL` = `gpt-5.6-luna`

değişkenlerini oluşturun. İş akışı her gün İstanbul saatiyle 09:15'te
tetiklenir.

Otomasyonu durdurmak için `DAILY_PUBLISH_ENABLED` değerini `false` yapın.

## Yerel komutlar

```bash
python3 -m unittest discover -s tests -v
python3 scripts/publish_daily.py --dry-run
```

Gerçek yayın yerelde de yapılabilir; bunun için iki anahtarın ortam değişkeni
olarak verilmesi ve `--publish` kullanılması gerekir. Kabuk geçmişine anahtar
yazmamak için Secrets tabanlı GitHub Actions akışı önerilir.
