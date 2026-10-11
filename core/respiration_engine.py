python
def fetch_raw_data(self) -> pd.DataFrame | None:
    """فقط داده خام رو از یاهو می‌گیره"""
    try:
        raw = yf.download(
            self.ticker,
            period=self.period,
            interval=self.interval,
            progress=False,
        )
        if raw.empty:
            return None

        df = pd.DataFrame()
        df["Open"] = raw["Open"].iloc[:, 0]
        df["High"] = raw["High"].iloc[:, 0]
        df["Low"] = raw["Low"].iloc[:, 0]
        df["Close"] = raw["Close"].iloc[:, 0]
        df["Volume"] = raw.get("Volume", pd.Series(0, index=raw.index)).iloc[:, 0]
        df.dropna(inplace=True)
        return df
    except Exception:
        return None


def calculate_breathing_and_signals(self, df: pd.DataFrame) -> pd.DataFrame:
    """فقط محاسبات تنفس و سیگنال رو انجام می‌ده (موتور و اپتیکال قبلاً اجرا شدن)"""
    # اینجا کدهای مربوط به Breath_Radius، Weighted_Breath، 
    # Slaughter_Zone، Long_Zone، Target_Price، Stop_Loss و Signal_Success رو بذار
    # (بدون صدا زدن مجدد motor و optical)
    
    return df
