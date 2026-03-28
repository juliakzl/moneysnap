import sqlite3
import pandas as pd
from finapp.config import DB_PATH

with sqlite3.connect(DB_PATH) as conn:
    df = pd.read_sql("SELECT * FROM transactions LIMIT 5", conn)
    print(df.to_string())
    print("\nTypes:", df["type"].value_counts().to_dict())
    print("Amount nulls:", df["amount"].isna().sum())
    print("Amount zeros:", (df["amount"] == 0).sum())
    print("Date sample:", df["date"].head())
