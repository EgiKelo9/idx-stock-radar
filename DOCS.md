# **DOKUMEN SPESIFIKASI PENGEMBANGAN SISTEM**

## *Proyek: IDX Stock Radar (AI Automation Bot)*

&nbsp;

## **INFORMASI DOKUMEN**

&nbsp;

| Parameter | Keterangan |
| :---- | :---- |
| **Nomor Dokumen** | DOC-IDX-2026-001 |
| **Versi** | 1.0.0 |
| **Status** | Approved for Development |
| **Target Ekosistem** | Bursa Efek Indonesia (BEI / IDX) |
| **Klasifikasi** | Internal Engineering & Architecture |

### **Riwayat Revisi**

&nbsp;

| Versi | Tanggal | Penulis | Deskripsi Perubahan |
| :---- | :---- | :---- | :---- |
| 1.0.0 | 09 Sept 2026 | Tim Arsitektur Sistem | Finalisasi PRD, SRS, Spesifikasi Teknis, dan Kepatuhan Regulasi BEI |

# **1\. PRODUCT REQUIREMENTS DOCUMENT**

### **1.1 Ringkasan Eksekutif & Visi Produk**

IDX Stock Radar adalah platform automasi analitik berbasis server yang memantau pergerakan seluruh emiten di Bursa Efek Indonesia (BEI) secara otonom. Platform ini menggabungkan pemindaian teknikal kuantitatif, analisis mikrostruktur likuiditas (*orderbook* & *foreign flow*), serta inferensi bahasa alami (*Natural Language Processing*) terhadap aksi korporasi emiten guna menghasilkan sinyal perdagangan terstruktur secara *real-time*.

### 

### **1.2 Masalah & Solusi**

* **Masalah:** Trader retail mandiri kesulitan memantau 900+ emiten secara serentak selama jam bursa aktif, sering kali terlambat mendeteksi lonjakan volume, dan kerap terjebak pada saham gorengan/tidak likuid akibat ketiadaan filter risiko otomatis.  
* **Solusi:** Mesin pemindaian otomatis dengan sistem penyaringan bertingkat (*multi-layer funnel*) yang mengeliminasi saham berisiko tinggi sedini mungkin dan hanya menyalurkan sinyal ber probabilitas tinggi dengan batasan *Risk-to-Reward Ratio* (RRR) yang terukur.

### 

### **1.3 Target Pengguna**

* **Tipe Pengguna:** *Swing trader* dan *momentum trader* saham Indonesia yang memerlukan pemantauan sistematis tanpa harus menatap layar perdagangan sepanjang hari.

### 

### **1.4 Ruang Lingkup Sistem (Scope of Work)**

* **Dalam Lingkup (In-Scope):**  
  * Pengambilan data berkala (EOD dan intraday interval 5–15 menit).  
  * Pemfilteran ketat terhadap emiten Papan Pemantauan Khusus (FCA), emiten berstatus suspensi, dan saham dengan nilai transaksi harian \< Rp1 Miliar.  
  * Analisis Broker Flow (Bandarmologi) harian untuk mengukur konsentrasi transaksi dari broker top-buyer dan top-seller.  
  * Perhitungan indikator kuantitatif: Simple Moving Average (SMA), Relative Strength Index (RSI), Average True Range (ATR), serta Volume Relative Ratio.  
  * Analisis sentimen keterbukaan informasi emiten menggunakan LLM.  
  * Pengiriman sinyal perdagangan terstruktur ke Telegram Bot API.  
* **Di Luar Lingkup (Out-of-Scope):**  
  * Eksekusi transaksi otomatis (*direct order routing*) ke akun sekuritas nasabah.  
  * Pengelolaan dana investasi kolektif.  
  * Analisis instrumen waran terstruktur, reksa dana, maupun obligasi.

### 

### **1.5 User Stories & Acceptance Criteria**

&nbsp;

| ID | User Story | Acceptance Criteria |
| :---- | :---- | :---- |
| **US-01** | Pengguna ingin menerima peringatan lonjakan volume pada saham likuid. | Sinyal terpicu jika Volume intraday ≥ 1.5 × rata-rata volume 20 hari dan nilai transaksi harian ≥ Rp1 Miliar. |
| **US-02** | Pengguna ingin rencana trading instan (Entry, TP, SL). | Setiap sinyal wajib menyertakan: Entry Price, Stop Loss (maksimal toleransi 1.5 × ATR), Take Profit 1, Take Profit 2, dan RRR minimal 1:2. |
| **US-03** | Pengguna ingin verifikasi konteks berita emiten. | Sistem mengekstrak dokumen keterbukaan informasi terakhir dan memberikan skor sentimen terukur (-1.0 hingga \+1.0) sebelum sinyal dikirim. |

### **1.6 Metrik Keberhasilan (KPI)**

* **Kecepatan Pipeline:** Waktu proses dari *data fetch* hingga notifikasi Telegram terkirim ≤ 30 detik.  
* **Akurasi Sinyal:** Tingkat keberhasilan (*win rate*) ≥ 60% mencapai target Take Profit 1 pada pengujian berjalan (*forward test*).  
* **Efisiensi Risiko:** *Profit factor* portofolio uji coba mencapai ≥ 1.8.

# **2\. SOFTWARE REQUIREMENTS SPECIFICATION**

### **2.1 Kebutuhan Fungsional (Functional Requirements)**

* **FR-01 (Engine Penjadwalan Pasar):**  
  * Sistem hanya aktif pada hari kerja bursa (Senin–Jumat) selama Sesi I (09.00–12.00 WIB) dan Sesi II (13.30–16.00 WIB).  
  * Sistem otomatis nonaktif saat hari libur resmi bursa (*calendar holiday handler*).  
* **FR-02 (Penyaringan Emiten):**  
  * Mengeliminasi saham yang masuk dalam kriteria Papan Pemantauan Khusus (FCA) dan notasi khusus suspensi.  
  * Mengabaikan saham yang memiliki nilai *turnover* harian rata-rata 20 hari di bawah Rp1.000.000.000.  
* **FR-03 (Analisis Teknikal):**  
  * Menghitung indikator teknis standar: SMA 20, SMA 50, SMA 200, RSI 14, dan ATR 14\.  
  * Mendeteksi kondisi pembalikan arah harga (*oversold bounce*) atau penembusan area resistensi (*breakout*).  
* **FR-04 (Validasi AI Kualitatif):**  
  * Mengambil teks pengumuman keterbukaan informasi emiten dari API/feed berita bursa.  
  * Mengirimkan teks ke LLM untuk dievaluasi terhadap kategori dampak: Laporan Keuangan, Dividen, Aksi Korporasi, atau Risiko Hukum/PKPU.  
* **FR-05 (Manajemen Risiko & Fraksi Harga):**  
  * Membulatkan seluruh level harga Entry, SL, dan TP sesuai ketentuan fraksi harga (*tick size*) resmi BEI.  
  * Membatalkan sinyal beli jika harga emiten sudah berada ≤ 1.5% dari batas *Auto Rejection Atas* (ARA).  
* **FR-06 (Distribusi Notifikasi):**  
  * Mengirimkan pesan terformat (Markdown) ke ID kanal/grup Telegram yang ditentukan.  
* **FR-07 (Analisis Broker Flow / Bandarmologi):**  
  * Sistem melakukan pelacakan transaksi harian berdasarkan aktivitas broker harian di bursa.  
  * Menghitung rasio akumulasi dari 3 broker pembeli terbesar (Net Buy Top 3\) terhadap total volume transaksi harian saham tersebut.  
  * Mengklasifikasikan status aliran dana broker menjadi empat kategori: Big Accumulation, Small Accumulation, Neutral, Small Distribution, dan Big Distribution.

&nbsp;

### **2.2 Kebutuhan Non-Fungsional (Non-Functional Requirements)**

* **NFR-01 (Ketersediaan / Uptime):** Sistem memiliki tingkat ketersediaan minimal 99.5% selama jam bursa berlangsung.  
* **NFR-02 (Ketahanan / Fault Tolerance):** Apabila terjadi kegagalan jaringan atau *timeout* pada API penyedia data, sistem melakukan *retry* maksimal 3 kali dengan jeda eksponensial (2 detik, 4 detik, 8 detik).  
* **NFR-03 (Keamanan):** Kunci privat (API key, token bot, database credential) disimpan dalam variabel lingkungan (*environment variables*) dan dilarang masuk ke dalam *version control system* (Git).

# **3\. TECHNICAL SPECIFICATION**

### **3.1 Arsitektur Sistem**

&nbsp;

```
+-----------------------------------------------------------------------------------+ 
|                             SERVER CONTAINER (DOCKER)                             | 
|                                                                                   | 
|   +-----------------------+              +-----------------------------------+    | 
|   |   Market Ingestion    |              |          PostgreSQL 16            |    | 
|   |  (APScheduler/Cron)   |              |          (TimescaleDB)            |    | 
|   +-----------+-----------+              +-----------------+-----------------+    | 
|               |                                            ^                      | 
|          (Raw Ticks)                                  (Audit Logs)                | 
|               v                                            |                      | 
|   +-----------------------+              +-----------------+-----------------+    | 
|   | Quantitative Screener |------------->|      LLM Sentiment Engine         |    | 
|   | (Pandas / TA Engine)  |              |     (OpenAI / Claude API)        |    | 
|   +-----------------------+              +-----------------+-----------------+    | 
|                                                            |                      | 
|                                                    (Validated Signal)             | 
|                                                            v                      | 
|   +-----------------------+              +-----------------------------------+    | 
|   |     Telegram API      |<-------------|        Signal Risk Engine         |    | 
|   |   (HTTP Dispatcher)   |              |     (Tick & Size Calculator)      |    | 
|   +-----------------------+              +-----------------------------------+    | 
+-----------------------------------------------------------------------------------+ 
```

### 

### **3.2 Tumpukan Teknologi (Tech Stack)**

* **Bahasa Pemrograman:** Python 3.11+  
* **Komputasi & Analisis:** Pandas, NumPy, TA-Lib (atau ta library)  
* **Basis Data:** PostgreSQL 16 dengan ekstensi TimescaleDB  
* **Model AI Kualitatif:** OpenAI GPT-4o-mini / Claude 3.5 Haiku (via API)  
* **Manajemen Proses:** Docker Engine & Docker Compose  
* **Notifikasi:** Telegram Bot API via requests / httpx

### 

### **3.3 Skema Basis Data (Database Schema)**

&nbsp;

```sql
-- 1. Tabel Master Emiten
CREATE TABLE master_tickers (
    symbol VARCHAR(10) PRIMARY KEY, -- Contoh: BBCA.JK
    company_name VARCHAR(255) NOT NULL,
    board VARCHAR(50) NOT NULL,     -- UTAMA, PENGEMBANGAN, FCA
    is_active BOOLEAN DEFAULT TRUE,
    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. Hypertable Time-Series Data Harga Saham
CREATE TABLE market_data (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(10) REFERENCES master_tickers(symbol),
    open NUMERIC(10, 2) NOT NULL,
    high NUMERIC(10, 2) NOT NULL,
    low NUMERIC(10, 2) NOT NULL,
    close NUMERIC(10, 2) NOT NULL,
    volume BIGINT NOT NULL,
    turnover NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (time, symbol)
);
SELECT create_hypertable('market_data', 'time', if_not_exists => TRUE);

-- 3. Tabel Log Eksekusi Sinyal
CREATE TABLE signal_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR(10) REFERENCES master_tickers(symbol),
    entry_price NUMERIC(10, 2) NOT NULL,
    stop_loss NUMERIC(10, 2) NOT NULL,
    take_profit_1 NUMERIC(10, 2) NOT NULL,
    take_profit_2 NUMERIC(10, 2) NOT NULL,
    risk_reward_ratio NUMERIC(4, 2) NOT NULL,
    volume_ratio NUMERIC(4, 2) NOT NULL,
    sentiment_score NUMERIC(3, 2),
    sentiment_summary TEXT,
    execution_status VARCHAR(20) DEFAULT 'SENT'
);
```

### 

### **3.4 Spesifikasi Payload Data**

#### 

#### **Format JSON Response Analisis Sentimen (LLM Engine):**

&nbsp;

```json
{
  "ticker": "BMRI",
  "sentiment_score": 0.85,
  "sentiment_label": "POSITIVE",
  "catalyst_event": "DIVIDEND_ANNOUNCEMENT",
  "summary": "Rapat Umum Pemegang Saham Tahunan menyetujui pembagian dividen tunai dengan yield estimasi mencapai 6.2%.",
  "risk_flags": []
}
```

#### 

#### **Format JSON Kontrak Sinyal (Alert Dispatcher):**

&nbsp;

```json
{
  "signal_id": "c1f72a44-8d19-4f81-9b16-562db4c80e12",
  "timestamp": "2026-09-09T10:30:00+07:00",
  "ticker": "BBRI",
  "setup_type": "PULLBACK_REBOUND",
  "parameters": {
    "entry": 4950,
    "stop_loss": 4800,
    "take_profit_1": 5250,
    "take_profit_2": 5450,
    "rrr": 2.0
  },
  "metrics": {
    "rsi": 41.2,
    "volume_multiplier": 2.3,
    "foreign_accum_rank": "HIGH",
    "broker_accum_rank": "BIG_ACCUM"
  },
  "ai_context": "Kinerja pertumbuhan kredit mikro stabil di atas rata-rata industri."
}
```

### 

### **3.5 Spesifikasi Notifikasi Telegram**

Sinyal perdagangan yang lolos dari penyaringan teknikal, broker flow, dan analisis sentimen dikirimkan ke Telegram dalam format teks Markdown.

&nbsp;

#### **Template Teks Notifikasi Telegram:**

&nbsp;

```
🚨 **IDX STOCK RADAR - NEW SIGNAL** 🚨

**Ticker:** ${ticker} (${company_name})
**Setup Type:** ${setup_type}

📈 **TRADING PLAN**
• **Entry Price:** Rp${entry}
• **Stop Loss:** Rp${stop_loss}
• **Take Profit 1:** Rp${take_profit_1}
• **Take Profit 2:** Rp${take_profit_2}
• **Risk-to-Reward Ratio (RRR):** 1:${rrr}

📊 **METRICS & ANALYSIS**
• **RSI (14):** ${rsi}
• **Volume Multiplier:** ${volume_multiplier}x (vs Rata-rata 20 Hari)
• **Foreign Flow:** ${foreign_accum_rank}
• **Broker Flow (Bandarmologi):** ${broker_accum_rank}

🤖 **AI SENTIMENT CONTEXT**
"${ai_context}"

⚠️ **DISCLAIMER ON**
*Analisis ini digenerasi secara otonom oleh bot komputasi untuk tujuan riset dan pencatatan pribadi. Bukan merupakan nasihat keuangan atau ajakan jual-beli efek sebagaimana diatur dalam regulasi OJK. Risiko investasi ditanggung sepenuhnya oleh masing-masing pelaku pasar.*
```

&nbsp;

# **4\. KEPATUHAN REGULASI DAN ATURAN PERDAGANGAN BEI**

### **4.1 Logika Batasan Harga Harian (Auto Rejection Simetris)**

Sistem wajib mengkonfirmasi batas fluktuasi harga harian sebelum memvalidasi sinyal beli:

&nbsp;

| Rentang Harga Saham | Persentase ARA / ARB |
| :---- | :---- |
| Rp50 – Rp200 | ± 35% |
| \> Rp200 – Rp5.000 | ± 25% |
| \> Rp5.000 | ± 20% |

*Aturan Eksekusi:* Jika current\_price \>= (ara\_limit \- (2 \* tick\_size)), sinyal langsung dibatalkan guna memitigasi risiko pesanan tidak tereksekusi.

### 

### **4.2 Fraksi Harga (Tick Size Rules)**

Seluruh kalkulasi level Entry, Stop Loss, dan Target Profit dibulatkan secara otomatis ke tick resmi:

&nbsp;

| Rentang Harga | Fraksi Harga (Tick) | Maksimal Perubahan Per Tick |
| :---- | :---- | :---- |
| \< Rp200 | Rp1 | Rp10 |
| Rp200 – Rp500 | Rp2 | Rp20 |
| Rp500 – Rp2.000 | Rp5 | Rp50 |
| Rp2.000 – Rp5.000 | Rp10 | Rp100 |
| ≥ Rp5.000 | Rp25 | Rp250 |

### **4.3 Kepatuhan Hukum OJK (Penafian Resmi)**

Setiap keluaran pesan ke pengguna diwajibkan memuat klausa penafian:

Setiap notifikasi dan sinyal yang dihasilkan oleh sistem wajib menyertakan pernyataan penafian resmi sebagai berikut:

**⚠️ DISCLAIMER ON:**  
*Analisis ini digenerasi secara otonom oleh bot komputasi untuk tujuan riset dan pencatatan pribadi. Bukan merupakan nasihat keuangan atau ajakan jual-beli efek sebagaimana diatur dalam regulasi OJK. Risiko investasi ditanggung sepenuhnya oleh masing-masing pelaku pasar.*

# **5\. RENCANA PELAKSANAAN & TAHAPAN IMPLEMENTASI**

&nbsp;

| Fase | Nama Siklus | Durasi | Target Capaian (Deliverables) |
| :---- | :---- | :---- | :---- |
| **Fase 1** | Ingestion & Basis Data | Minggu 1–2 | Skrip penarik data pasar, setup tabel TimescaleDB, filter emiten FCA. |
| **Fase 2** | Quantitative Core | Minggu 3–4 | Modul indikator teknikal (SMA, RSI, ATR, Volume Spike), kalkulator tick size BEI. |
| **Fase 3** | AI & Sentiment Integration | Minggu 5 | Pipeline pengolahan berita emiten, prompt parser terstruktur, integrasi LLM API. |
| **Fase 4** | Risk Manager & Telegram Bot | Minggu 6 | Integrasi bot alert Telegram, manajemen format pesan, kalkulator RRR. |
| **Fase 5** | Backtesting & Validasi | Minggu 7 | Pengujian balik dengan data historis 2 tahun terakhir; kalibrasi bobot sinyal. |
| **Fase 6** | Deployment & Forward Testing | Minggu 8+ | Penerapan sistem di VPS Docker, uji coba paper trading selama 30 hari jam bursa aktif. |

# **6\. PROSEDUR OPERASIONAL & PENANGANAN MASALAH (RUNBOOK)**

### **6.1 Setup Lingkungan Mandiri (docker-compose.yml)**

&nbsp;

```
version: '3.8'

services:
  database:
    image: timescale/timescaledb:latest-pg16
    container_name: idx_timescale_db
    restart: always
    environment:
      POSTGRES_USER: ${DB_USER:-postgres}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-idxpassword}
      POSTGRES_DB: idx_market_db
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  scanner_service:
    build: .
    container_name: idx_scanner_engine
    restart: unless-stopped
    depends_on:
      - database
    env_file:
      - .env
    command: python scheduler.py

volumes:
  pgdata:
```

### 

### **6.2 Matriks Penanganan Insiden (Troubleshooting)**

* **Kondisi: API Data Penyedia Macet (Rate-Limited)**  
  * *Tindakan:* Periksa log pada container, ubah interval permintaan data dari 15 menit menjadi 30 menit, dan aktifkan mekanisme rotasi API key atau beralih ke cache data historis lokal.  
* **Kondisi: Lonjakan Latensi Ekstraksi LLM**  
  * *Tindakan:* Batasi input token berita maksimal 500 kata pertama, set parameter max\_tokens: 150, dan aktifkan *fallback* sinyal berbasis teknikal murni jika LLM API mengalami *timeout* \> 10 detik.  
* **Kondisi: Basis Data Terputus**  
  * *Tindakan:* Service scanner menyimpan sinyal darurat dalam memori lokal (*flat file buffer*) dan langsung mengirimkan sinyal ke Telegram tanpa jeda penyimpanan database sampai koneksi pulih kembali.