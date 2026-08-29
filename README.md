# METU ODTUClass MCP Server 🚀

ODTÜ'nün Moodle tabanlı eğitim yönetim sistemi olan **ODTUClass** (`odtuclass.metu.edu.tr`) için geliştirilmiş **Model Context Protocol (MCP) Sunucusu**dur. Python ve `FastMCP` kullanılarak geliştirilmiştir.

Antigravity AI asistanı, Claude Desktop ve diğer MCP destekli LLM istemcileriyle doğrudan entegre olarak öğrencilerin derslerini, duyurularını, izlencelerini (syllabus), ödev teslim tarihlerini ve laboratuvar/recitation saatlerini sorgulamasını sağlar.

---

## 🛠️ Sunulan MCP Araçları (Tools)

Sunucu aşağıdaki 5 temel MCP aracını sunar:

| MCP Aracı (Tool) | Parametreler | Açıklama |
| :--- | :--- | :--- |
| **`get_enrolled_courses`** | `student_token: str` | Öğrencinin aktif kayıtlı olduğu tüm dersleri, ders ID'lerini, kodlarını ve web bağlantılarını listeler. |
| **`get_course_announcements`** | `course_id: str`, `student_token: str`, `limit: int = 5` | İlgili dersin duyuru panosundaki en son duyuruları (başlık, yazar, tarih, temizlenmiş metin ve ek dosya linkleri) getirir. |
| **`get_course_syllabus`** | `course_id: str`, `student_token: str` | Dersin sayfasındaki Syllabus / Ders İzlencesi PDF'lerini, linklerini veya genel ders politikasını bulup özetler. |
| **`get_upcoming_assignments`** | `student_token: str` | Takvim ve ödevler bölümünden teslim tarihi yaklaşan ödevleri, quiz'leri, kalan süreleri (örn. *2 gün 4 saat kaldı*) ve teslim linklerini listeler. |
| **`get_lab_recitation_info`** | `course_code: str`, `section: int`, `student_token: str` | İlgili dersin içerik ve duyurularını tarayarak öğrencinin seçtiği **Section / Şube**ye ait haftalık Lab / Recitation saatini, dersliğini ve ilgili duyuruları çeker. |

---

## 🔑 Kimlik Doğrulama Seçenekleri (Authentication)

Sunucuya bağlanmak için iki yöntemden birini kullanabilirsiniz:

### Yöntem 1: ODTÜ Kullanıcı Adı ve Şifre ile Otomatik Giriş (Önerilen)
Moodle web servis tokenı almakla uğraşmak istemiyorsanız, doğrudan METU kullanıcı adı ve şifrenizi tanımlayabilirsiniz:
- Ortam değişkenleri: `ODTUCLASS_USERNAME` ve `ODTUCLASS_PASSWORD`
- Veya AI asistanına doğrudan `login(username, password)` komutunu çağırtabilirsiniz. Sunucu `/login/token.php` servisi üzerinden tokenı otomatik edinir.

### Yöntem 2: ODTUClass Web Servis Tokenı (Security Key) ile
1. Tarayıcınızdan [ODTUClass](https://odtuclass.metu.edu.tr) adresine giriş yapın.
2. Sağ üst köşedeki **Profil Resminize / Adınıza** tıklayın ve **Preferences (Tercihler)** seçeneğine gidin.
3. **User Account (Kullanıcı Hesabı)** altında yer alan **Security keys (Güvenlik anahtarları)** bağlantısına tıklayın.
4. **Moodle mobile web service** için tanımlı 32 karakterlik tokenı kopyalayın ve `ODTUCLASS_TOKEN` olarak tanımlayın.

---

## 📦 Kurulum

### 1. Gereksinimler
- Python 3.10 veya üzeri
- `pip` veya `uv`

### 2. Bağımlılıkları Yükleme
```bash
pip install -r requirements.txt
```

---

## ⚙️ MCP İstemci Yapılandırması

### Antigravity IDE Yapılandırması (`mcp_config.json`)
Antigravity konfigürasyonunuza (`.agents/mcp_config.json` veya global `.gemini/config/mcp_config.json`) aşağıdaki tanımı ekleyebilirsiniz:

#### Kullanıcı Adı & Şifre ile:
```json
{
  "mcpServers": {
    "odtuclass": {
      "command": "c:/Users/Asus/Documents/Development/repos/metu-odtuclass-mcp/.venv/Scripts/python.exe",
      "args": [
        "c:/Users/Asus/Documents/Development/repos/metu-odtuclass-mcp/odtuclass_mcp.py"
      ],
      "env": {
        "ODTUCLASS_BASE_URL": "https://odtuclass.metu.edu.tr",
        "ODTUCLASS_USERNAME": "e123456",
        "ODTUCLASS_PASSWORD": "sifreniz"
      }
    }
  }
}
```

#### Veya Token ile:
```json
{
  "mcpServers": {
    "odtuclass": {
      "command": "c:/Users/Asus/Documents/Development/repos/metu-odtuclass-mcp/.venv/Scripts/python.exe",
      "args": [
        "c:/Users/Asus/Documents/Development/repos/metu-odtuclass-mcp/odtuclass_mcp.py"
      ],
      "env": {
        "ODTUCLASS_BASE_URL": "https://odtuclass.metu.edu.tr",
        "ODTUCLASS_TOKEN": "<32_KARAKTERLIK_TOKEN>"
      }
    }
  }
}
```

### Claude Desktop Yapılandırması (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "odtuclass": {
      "command": "python",
      "args": [
        "c:/Users/Asus/Documents/Development/repos/metu-odtuclass-mcp/odtuclass_mcp.py"
      ]
    }
  }
}
```

---

## 🚀 Sunucuyu Çalıştırma

Doğrudan çalıştırmak için:
```bash
python odtuclass_mcp.py
```

FastMCP geliştirici arayüzü ile test etmek için:
```bash
mcp dev odtuclass_mcp.py
```

---

## 🧪 Testleri Çalıştırma

Birim ve mock testleri çalıştırmak için:
```bash
python -m unittest discover tests
```

---

## 📁 Proje Mimarisi

```
metu-odtuclass-mcp/
├── odtuclass_mcp.py      # FastMCP sunucu tanımı ve 5 MCP Tool fonksiyonu
├── odtuclass_client.py   # ODTUClass Moodle REST API istemcisi ve içerik ayrıştırıcı
├── models.py             # Pydantic veri modelleri ve tip tanımları
├── requirements.txt      # Bağımlılıklar (mcp, httpx, beautifulsoup4, pydantic)
├── pyproject.toml        # Proje paket yapılandırması
├── tests/                # Birim testler ve mock senaryoları
│   ├── __init__.py
│   └── test_odtuclass.py
└── README.md             # Kılavuz ve dokümantasyon
```

---

## 📄 Lisans
Bu proje [LICENSE](file:///c:/Users/Asus/Documents/Development/repos/metu-odtuclass-mcp/LICENSE) kapsamında lisanslanmıştır.