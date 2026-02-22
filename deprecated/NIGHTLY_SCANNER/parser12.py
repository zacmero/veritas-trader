import json
import os
import re
import time
from datetime import date, timedelta

import finnhub
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from dateutil import parser
from gnews import GNews
# from pysentimiento import create_analyzer (deprecated)
from tqdm import tqdm

# === Configurações básicas ===
METADATA_PATH = "nasdaq_stable_metadata.json"
OUTPUT_DIR = "stocks_news"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === APIs ===
gn = GNews(language="en", country="US", max_results=100)
finnhub_client = finnhub.Client(api_key="d48dom1r01qnpsnnbev0")

# === Fontes confiáveis ===
trusted_sites = [
    "www.reuters.com",
    "www.bloomberg.com",
    "www.marketwatch.com",
    "www.wsj.com",
    "www.cnbc.com",
    "www.nasdaq.com",
    "www.investing.com",
    "www.barrons.com",
    "www.morningstar.com",
    "www.fool.com",
    "seekingalpha.com",
    "www.marketbeat.com",
    "www.tipranks.com",
    "www.investors.com",
    "www.zacks.com",
    "www.nytimes.com/section/business",
    "www.forbes.com",
    "www.businessinsider.com",
    "www.usatoday.com/money",
    "www.ft.com",
    "www.economist.com",
    "techcrunch.com",
    "www.theverge.com",
    "www.engadget.com",
    "www.cnet.com",
    "www.arstechnica.com",
]
query_sites = " OR ".join([f"site:{site}" for site in trusted_sites])

# === Datas ===
today = date.today()
start_date = today - timedelta(days=30)

# === Inicializa o analisador de sentimentos ===
analyzer = create_analyzer(task="sentiment", lang="en")


def classify_headline(text):
    """Classifica um título e retorna um score contínuo de sentimento."""
    result = analyzer.predict(str(text))
    pos = result.probas.get("POS", 0)
    neg = result.probas.get("NEG", 0)
    neu = result.probas.get("NEU", 0)

    total = pos + neg
    if total == 0:
        pos_final, neg_final = 0.5, 0.5
    else:
        pos_final = pos + (pos / total) * neu
        neg_final = neg + (neg / total) * neu

    return pos_final - neg_final


# === Funções auxiliares ===
def convert_datetime(df):
    if "datetime" in df.columns:
        df["Published"] = pd.to_datetime(df["datetime"], unit="s")
    elif "date" in df.columns:
        df["Published"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def _make_pattern(symbol: str, name: str) -> re.Pattern:
    escaped_name = re.escape(name) if name else ""
    escaped_symbol = re.escape(symbol) if symbol else ""
    pattern_str = f"(?i)\\b({escaped_symbol}|{escaped_name})\\b"
    return re.compile(pattern_str, flags=re.IGNORECASE)


def fetch_company_news_gnews(symbol, name):
    query = f"({name or symbol}) ({query_sites})"
    try:
        results = gn.get_news(query)
    except Exception as e:
        print(f"[WARN] GNews error for {symbol}: {e}")
        return pd.DataFrame()

    if not results:
        return pd.DataFrame()

    parsed_results = []
    for item in results:
        published_raw = item.get("published date", "")
        try:
            published_date = parser.parse(published_raw).isoformat()
        except Exception:
            published_date = ""

        parsed_results.append(
            {
                "Symbol": symbol,
                "Title": item.get("title", ""),
                "Source": item.get("publisher", {}).get("title", "N/A")
                if "publisher" in item
                else "N/A",
                "Description": item.get("description", ""),
                "Published": published_date,
                "URL": item.get("url", ""),
            }
        )

    df = pd.DataFrame(parsed_results)
    if df.empty:
        return df

    pattern = _make_pattern(symbol, name)
    mask = df["Title"].str.contains(pattern) | df["Description"].str.contains(pattern)
    df = df[mask]

    return df


def fetch_company_news_finnhub(symbol, name, target_date):
    # Use the provided target_date to define the search window
    end_date = target_date
    start_date = end_date - timedelta(days=30)
    
    try:
        data = finnhub_client.company_news(
            symbol, _from=start_date.strftime("%Y-%m-%d"), to=end_date.strftime("%Y-%m-%d")
        )
    except Exception as e:
        print(f"[WARN] Finnhub error for {symbol}: {e}")
        return pd.DataFrame()

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df = convert_datetime(df)

    if df.empty or "headline" not in df.columns:
        return pd.DataFrame()

    pattern = _make_pattern(symbol, name)
    df = df[df["headline"].str.contains(pattern, na=False)]

    df = df.rename(columns={"headline": "Title", "source": "Source", "url": "URL"})
    return df[["Published", "Title", "Source", "URL"]]


def fetch_news_for_symbols(symbols, sector=None, save=True, target_date=None):
    # === 0. Define the date range ===
    if target_date:
        today = target_date
    else:
        today = date.today()
    start_date = today - timedelta(days=30)
    # === 1. Carrega metadados ===
    if not os.path.exists(METADATA_PATH):
        raise FileNotFoundError(
            f"{METADATA_PATH} not found. Run the metadata script first."
        )

    with open(METADATA_PATH, "r") as f:
        metadata = json.load(f)
    df_meta = pd.DataFrame(metadata)

    # === 2. Filtro por setor (opcional) ===
    if sector:
        df_meta = df_meta[df_meta["sector"] == sector]

    # === 3. Filtro por símbolos ===
    df_meta = df_meta[df_meta["Symbol"].isin(symbols)]

    if df_meta.empty:
        print("[INFO] No valid symbols found in metadata.")
        return pd.DataFrame()

    all_results = []

    for _, row in tqdm(
        df_meta.iterrows(), total=len(df_meta), desc="Fetching company news"
    ):
        symbol = row.get("Symbol", "")
        name = row.get("Name", "")

        print(f"\n=== Fetching news for {symbol} ({name}) ===")

        df_gnews = fetch_company_news_gnews(symbol, name)
        df_finnhub = fetch_company_news_finnhub(symbol, name, today)
        time.sleep(0.3)

        df_all = pd.concat([df_gnews, df_finnhub], ignore_index=True)
        if df_all.empty:
            continue

        # === Calcula o sentimento ===
        df_all["Score"] = df_all["Title"].apply(classify_headline)

        # === Salva ===
        if save:
            output = os.path.join(OUTPUT_DIR, f"{symbol}.csv")
            df_all.to_csv(output, index=False, encoding="utf-8")
            print(f"✅ Saved: {output}")

        all_results.append(df_all)

    if all_results:
        df_final = pd.concat(all_results, ignore_index=True)
        return df_final
    else:
        print("\n⚠️ No news matched nominal symbol/name criteria.")
        return pd.DataFrame()


# ============================================================
# === Exemplo de uso ===
# ============================================================
if __name__ == "__main__":
    selected_symbols = ["AAPL"]
    df_news = fetch_news_for_symbols(selected_symbols, sector="Technology", save=True)
    print(df_news.head())

    # === Scatterplot de sentimento ===
    if not df_news.empty:
        df_news["Published"] = pd.to_datetime(df_news["Published"], errors="coerce")
        df_news = df_news.dropna(subset=["Published", "Score"])

        sns.scatterplot(data=df_news, x="Published", y="Score", color="blue", alpha=0.6)
        plt.title("Sentiment Scores Over Time - AAPL")
        plt.xlabel("Date")
        plt.ylabel("Sentiment Score")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()
