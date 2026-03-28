# Popular ETFs available on Trade Republic, with Yahoo Finance tickers (.DE = Xetra/Frankfurt)
# Format: {"name": display name, "ticker": Yahoo Finance ticker, "category": group label}

ETF_CATALOG = [
    # --- Global ---
    {"name": "iShares Core MSCI World",             "ticker": "EUNL.DE",  "category": "Global"},
    {"name": "Amundi MSCI World",                   "ticker": "MWRE.DE",  "category": "Global"},
    {"name": "Xtrackers MSCI World Swap",           "ticker": "DBXW.DE",  "category": "Global"},
    {"name": "Vanguard FTSE All-World (Acc)",       "ticker": "VWCE.DE",  "category": "Global"},
    {"name": "Vanguard FTSE All-World (Dist)",      "ticker": "VWRL.DE",  "category": "Global"},
    {"name": "iShares MSCI ACWI",                   "ticker": "IUSQ.DE",  "category": "Global"},
    {"name": "SPDR MSCI ACWI IMI",                  "ticker": "SPYI.DE",  "category": "Global"},

    # --- USA ---
    {"name": "iShares Core S&P 500",                "ticker": "SXR8.DE",  "category": "USA"},
    {"name": "Vanguard S&P 500 (Acc)",              "ticker": "VUAA.DE",  "category": "USA"},
    {"name": "Xtrackers S&P 500 Swap",              "ticker": "XSPX.DE",  "category": "USA"},
    {"name": "Amundi S&P 500",                      "ticker": "SPXS.DE",  "category": "USA"},
    {"name": "iShares Core S&P 500 (Dist)",         "ticker": "IUSA.DE",  "category": "USA"},
    {"name": "iShares Nasdaq 100",                  "ticker": "SXRV.DE",  "category": "USA"},
    {"name": "Invesco Nasdaq 100",                  "ticker": "EQQQ.DE",  "category": "USA"},
    {"name": "Xtrackers MSCI USA",                  "ticker": "XD9U.DE",  "category": "USA"},

    # --- Europe ---
    {"name": "iShares Core EURO STOXX 50",          "ticker": "EXW1.DE",  "category": "Europe"},
    {"name": "iShares STOXX Europe 600",            "ticker": "EXSA.DE",  "category": "Europe"},
    {"name": "Vanguard FTSE Developed Europe",      "ticker": "VEUR.DE",  "category": "Europe"},
    {"name": "Amundi EURO STOXX 50",               "ticker": "C50.DE",   "category": "Europe"},
    {"name": "Xtrackers EURO STOXX 50",             "ticker": "DXET.DE",  "category": "Europe"},
    {"name": "iShares MSCI Europe",                 "ticker": "IMAE.DE",  "category": "Europe"},

    # --- Emerging Markets ---
    {"name": "iShares Core MSCI EM IMI",            "ticker": "IS3N.DE",  "category": "Emerging Markets"},
    {"name": "Xtrackers MSCI Emerging Markets",     "ticker": "XMEM.DE",  "category": "Emerging Markets"},
    {"name": "Vanguard FTSE Emerging Markets",      "ticker": "VFEM.DE",  "category": "Emerging Markets"},
    {"name": "iShares MSCI EM",                     "ticker": "IEMS.DE",  "category": "Emerging Markets"},

    # --- Sectors ---
    {"name": "iShares Global Clean Energy",         "ticker": "IQQH.DE",  "category": "Sector"},
    {"name": "iShares Automation & Robotics",       "ticker": "RBOT.DE",  "category": "Sector"},
    {"name": "iShares Digital Security",            "ticker": "LOCK.DE",  "category": "Sector"},
    {"name": "iShares Healthcare Innovation",       "ticker": "HEAL.DE",  "category": "Sector"},
    {"name": "Xtrackers MSCI World IT",             "ticker": "XWIT.DE",  "category": "Sector"},
    {"name": "iShares MSCI World Financials",       "ticker": "QDVF.DE",  "category": "Sector"},

    # --- Dividends ---
    {"name": "Vanguard FTSE All-World High Div",    "ticker": "VHYL.DE",  "category": "Dividends"},
    {"name": "iShares MSCI World Quality Dividend", "ticker": "WQDV.DE",  "category": "Dividends"},
    {"name": "iShares STOXX Global Sel Div 100",    "ticker": "EXX5.DE",  "category": "Dividends"},
    {"name": "Xtrackers MSCI World High Dividend",  "ticker": "XDWD.DE",  "category": "Dividends"},

    # --- ESG / SRI ---
    {"name": "iShares MSCI World ESG Screened",     "ticker": "SAWD.DE",  "category": "ESG"},
    {"name": "Amundi MSCI World SRI",               "ticker": "WSRI.DE",  "category": "ESG"},
    {"name": "Xtrackers MSCI World ESG",            "ticker": "XZWD.DE",  "category": "ESG"},
    {"name": "iShares MSCI EM ESG Screened",        "ticker": "SASU.DE",  "category": "ESG"},

    # --- Bonds ---
    {"name": "iShares Global Aggregate Bond",       "ticker": "AGGG.DE",  "category": "Bonds"},
    {"name": "Vanguard Global Aggregate Bond",      "ticker": "VAGP.DE",  "category": "Bonds"},
    {"name": "iShares € Corp Bond",                 "ticker": "IEAC.DE",  "category": "Bonds"},
    {"name": "iShares € Govt Bond 7-10yr",          "ticker": "IBCI.DE",  "category": "Bonds"},
    {"name": "Xtrackers Global Government Bond",    "ticker": "XGSG.DE",  "category": "Bonds"},

    # --- Commodities ---
    {"name": "iShares Physical Gold ETC",           "ticker": "EGLN.DE",  "category": "Commodities"},
    {"name": "Xtrackers Physical Gold ETC",         "ticker": "XAD1.DE",  "category": "Commodities"},
    {"name": "iShares Diversified Commodity Swap",  "ticker": "COMM.DE",  "category": "Commodities"},
]
