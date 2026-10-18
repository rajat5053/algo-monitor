"""
Instrument configuration for monitored assets.

Each exchange has its own instrument list.  Instruments are loaded from a
YAML-like Python dict so they can be extended without touching strategy code.

Market categories:
    - "indian"  → NSE indices + F&O securities (via Upstox)
    - "crypto"  → Spot, perpetual futures, options (via Delta Exchange)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Exchange(str, Enum):
    UPSTOX = "upstox"
    DELTA = "delta"


class AssetClass(str, Enum):
    INDEX = "index"
    EQUITY = "equity"
    SPOT_CRYPTO = "spot_crypto"
    PERP_FUTURE = "perpetual_future"
    FUTURE = "future"
    OPTION = "option"


class TradingMode(str, Enum):
    INTRADAY = "intraday"
    SWING = "swing"
    BOTH = "both"


class MarketCategory(str, Enum):
    INDIAN = "indian"
    CRYPTO = "crypto"


@dataclass
class Instrument:
    """A single tradeable/monitorable instrument."""

    symbol: str
    exchange: Exchange
    asset_class: AssetClass
    market_category: MarketCategory = MarketCategory.INDIAN
    trading_mode: TradingMode = TradingMode.BOTH
    display_name: str = ""

    # Index membership (for F&O grouping)
    index_membership: str = ""  # e.g. "nifty50,banknifty"

    # Upstox-specific
    instrument_key: str = ""  # e.g. "NSE_INDEX|Nifty 50"

    # Delta-specific
    delta_product_id: int | None = None

    # Filtering thresholds (set to 0 to skip checks)
    min_24h_volume: float = 0
    min_liquidity_score: float = 0

    # Whether to actively monitor this instrument
    enabled: bool = True

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.symbol


# ---------------------------------------------------------------------------
# Default instrument watchlist
# ---------------------------------------------------------------------------

DEFAULT_INSTRUMENTS: list[Instrument] = [
    # =====================================================================
    # INDIAN MARKET — Indices
    # =====================================================================
    Instrument(
        symbol="NIFTY50",
        exchange=Exchange.UPSTOX,
        asset_class=AssetClass.INDEX,
        market_category=MarketCategory.INDIAN,
        instrument_key="NSE_INDEX|Nifty 50",
        display_name="Nifty 50",
        trading_mode=TradingMode.INTRADAY,
    ),
    Instrument(
        symbol="BANKNIFTY",
        exchange=Exchange.UPSTOX,
        asset_class=AssetClass.INDEX,
        market_category=MarketCategory.INDIAN,
        instrument_key="NSE_INDEX|Nifty Bank",
        display_name="Bank Nifty",
        trading_mode=TradingMode.INTRADAY,
    ),
    Instrument(
        symbol="NIFTYAUTO",
        exchange=Exchange.UPSTOX,
        asset_class=AssetClass.INDEX,
        market_category=MarketCategory.INDIAN,
        instrument_key="NSE_INDEX|Nifty Auto",
        display_name="Nifty Auto",
        trading_mode=TradingMode.INTRADAY,
    ),
    Instrument(
        symbol="NIFTYMIDCAPSELECT",
        exchange=Exchange.UPSTOX,
        asset_class=AssetClass.INDEX,
        market_category=MarketCategory.INDIAN,
        instrument_key="NSE_INDEX|NIFTY MID SELECT",
        display_name="Nifty Midcap Select",
        trading_mode=TradingMode.INTRADAY,
    ),

    # =====================================================================
    # INDIAN MARKET — F&O Securities (Nifty 50 constituents)
    # =====================================================================
    Instrument(
        symbol="RELIANCE", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE002A01018",
        display_name="Reliance Industries", index_membership="nifty50",
    ),
    Instrument(
        symbol="TCS", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE467B01029",
        display_name="TCS", index_membership="nifty50",
    ),
    Instrument(
        symbol="HDFCBANK", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE040A01034",
        display_name="HDFC Bank", index_membership="nifty50,banknifty",
    ),
    Instrument(
        symbol="INFY", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE009A01021",
        display_name="Infosys", index_membership="nifty50",
    ),
    Instrument(
        symbol="ICICIBANK", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE090A01021",
        display_name="ICICI Bank", index_membership="nifty50,banknifty",
    ),
    Instrument(
        symbol="BHARTIARTL", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE397D01024",
        display_name="Bharti Airtel", index_membership="nifty50",
    ),
    Instrument(
        symbol="SBIN", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE062A01020",
        display_name="SBI", index_membership="nifty50,banknifty",
    ),
    Instrument(
        symbol="ITC", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE154A01025",
        display_name="ITC", index_membership="nifty50",
    ),
    Instrument(
        symbol="HINDUNILVR", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE030A01027",
        display_name="Hindustan Unilever", index_membership="nifty50",
    ),
    Instrument(
        symbol="KOTAKBANK", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE237A01036",
        display_name="Kotak Mahindra Bank", index_membership="nifty50,banknifty",
    ),
    Instrument(
        symbol="LT", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE018A01030",
        display_name="Larsen & Toubro", index_membership="nifty50",
    ),
    Instrument(
        symbol="AXISBANK", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE238A01034",
        display_name="Axis Bank", index_membership="nifty50,banknifty",
    ),

    # =====================================================================
    # INDIAN MARKET — F&O Securities (Bank Nifty specific)
    # =====================================================================
    Instrument(
        symbol="INDUSINDBK", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE095A01012",
        display_name="IndusInd Bank", index_membership="banknifty",
    ),
    Instrument(
        symbol="BANKBARODA", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE028A01039",
        display_name="Bank of Baroda", index_membership="banknifty",
    ),
    Instrument(
        symbol="FEDERALBNK", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE171A01029",
        display_name="Federal Bank", index_membership="banknifty",
    ),
    Instrument(
        symbol="PNB", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE160A01022",
        display_name="Punjab National Bank", index_membership="banknifty",
    ),
    Instrument(
        symbol="AUBANK", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE949L01017",
        display_name="AU Small Finance Bank", index_membership="banknifty",
    ),
    Instrument(
        symbol="IDFCFIRSTB", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE092T01019",
        display_name="IDFC First Bank", index_membership="banknifty",
    ),

    # =====================================================================
    # INDIAN MARKET — F&O Securities (Nifty Auto)
    # =====================================================================
    Instrument(
        symbol="TATAMOTORS", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE155A01022",
        display_name="Tata Motors", index_membership="niftyauto,nifty50",
    ),
    Instrument(
        symbol="M&M", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE101A01026",
        display_name="Mahindra & Mahindra", index_membership="niftyauto,nifty50",
    ),
    Instrument(
        symbol="MARUTI", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE585B01010",
        display_name="Maruti Suzuki", index_membership="niftyauto,nifty50",
    ),
    Instrument(
        symbol="BAJAJ-AUTO", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE917I01010",
        display_name="Bajaj Auto", index_membership="niftyauto,nifty50",
    ),
    Instrument(
        symbol="HEROMOTOCO", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE158A01026",
        display_name="Hero MotoCorp", index_membership="niftyauto",
    ),
    Instrument(
        symbol="EICHERMOT", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE066A01021",
        display_name="Eicher Motors", index_membership="niftyauto",
    ),
    Instrument(
        symbol="ASHOKLEY", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE208A01029",
        display_name="Ashok Leyland", index_membership="niftyauto",
    ),
    Instrument(
        symbol="BALKRISIND", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE787D01026",
        display_name="Balkrishna Industries", index_membership="niftyauto",
    ),
    Instrument(
        symbol="TVSMOTOR", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE494B01023",
        display_name="TVS Motor", index_membership="niftyauto",
    ),
    Instrument(
        symbol="MRF", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE883A01011",
        display_name="MRF", index_membership="niftyauto",
    ),

    # =====================================================================
    # INDIAN MARKET — F&O Securities (Nifty Midcap Select)
    # =====================================================================
    Instrument(
        symbol="DIXON", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE935N01020",
        display_name="Dixon Technologies", index_membership="niftymidcapselect",
    ),
    Instrument(
        symbol="PERSISTENT", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE262H01021",
        display_name="Persistent Systems", index_membership="niftymidcapselect",
    ),
    Instrument(
        symbol="MPHASIS", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE356A01018",
        display_name="Mphasis", index_membership="niftymidcapselect",
    ),
    Instrument(
        symbol="VOLTAS", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE226A01021",
        display_name="Voltas", index_membership="niftymidcapselect",
    ),
    Instrument(
        symbol="CUMMINSIND", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE298A01020",
        display_name="Cummins India", index_membership="niftymidcapselect",
    ),
    Instrument(
        symbol="INDHOTEL", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE053A01029",
        display_name="Indian Hotels", index_membership="niftymidcapselect",
    ),
    Instrument(
        symbol="FEDERALBNK_MID", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE171A01029",
        display_name="Federal Bank", index_membership="niftymidcapselect,banknifty",
        enabled=False,  # Already included in Bank Nifty above
    ),
    Instrument(
        symbol="OBEROIRLTY", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE093I01010",
        display_name="Oberoi Realty", index_membership="niftymidcapselect",
    ),
    Instrument(
        symbol="COFORGE", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE591G01025",
        display_name="Coforge", index_membership="niftymidcapselect",
    ),
    Instrument(
        symbol="SUPREMEIND", exchange=Exchange.UPSTOX, asset_class=AssetClass.EQUITY,
        market_category=MarketCategory.INDIAN, instrument_key="NSE_EQ|INE195A01028",
        display_name="Supreme Industries", index_membership="niftymidcapselect",
    ),

    # =====================================================================
    # CRYPTO MARKET — Standard USD Pairs (Perpetuals & Spot)
    # =====================================================================
    Instrument(
        symbol="BTCUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="BTC/USD Perpetual",
        min_24h_volume=100_000,
    ),
    Instrument(
        symbol="ETHUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="ETH/USD Perpetual",
        min_24h_volume=50_000,
    ),
    Instrument(
        symbol="SOLUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="SOL/USD Perpetual",
        min_24h_volume=10_000,
    ),
    Instrument(
        symbol="XRPUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="XRP/USD Perpetual",
        min_24h_volume=10_000,
    ),
    Instrument(
        symbol="BNBUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="BNB/USD Perpetual",
        min_24h_volume=5_000,
    ),
    Instrument(
        symbol="DOGEUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="DOGE/USD Perpetual",
        min_24h_volume=5_000,
    ),
    Instrument(
        symbol="AVAXUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="AVAX/USD Perpetual",
        min_24h_volume=5_000,
    ),
    Instrument(
        symbol="LINKUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="LINK/USD Perpetual",
        min_24h_volume=5_000,
    ),
    Instrument(
        symbol="NEARUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="NEAR/USD Perpetual",
        min_24h_volume=5_000,
    ),
    Instrument(
        symbol="DOTUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="DOT/USD Perpetual",
        min_24h_volume=5_000,
    ),
    Instrument(
        symbol="SUIUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="SUI/USD Perpetual",
        min_24h_volume=5_000,
    ),
    Instrument(
        symbol="PEPEUSD",
        exchange=Exchange.DELTA,
        asset_class=AssetClass.PERP_FUTURE,
        market_category=MarketCategory.CRYPTO,
        display_name="PEPE/USD Perpetual",
        min_24h_volume=5_000,
    ),
]


def get_enabled_instruments(
    exchange: Exchange | None = None,
    market_category: MarketCategory | None = None,
) -> list[Instrument]:
    """Return enabled instruments, optionally filtered by exchange or market category."""
    instruments = [i for i in DEFAULT_INSTRUMENTS if i.enabled]
    if exchange is not None:
        instruments = [i for i in instruments if i.exchange == exchange]
    if market_category is not None:
        instruments = [i for i in instruments if i.market_category == market_category]
    return instruments


def get_indices() -> list[Instrument]:
    """Return all index instruments."""
    return [
        i for i in DEFAULT_INSTRUMENTS
        if i.enabled and i.asset_class == AssetClass.INDEX
    ]


def get_fno_securities(index_filter: str = "") -> list[Instrument]:
    """
    Return F&O equity securities, optionally filtered by index membership.
    index_filter: e.g. 'nifty50', 'banknifty', 'niftyauto', 'niftymidcapselect'
    """
    instruments = [
        i for i in DEFAULT_INSTRUMENTS
        if i.enabled
        and i.asset_class == AssetClass.EQUITY
        and i.market_category == MarketCategory.INDIAN
    ]
    if index_filter:
        instruments = [
            i for i in instruments
            if index_filter.lower() in i.index_membership.lower()
        ]
    return instruments


def get_instrument(symbol: str) -> Instrument | None:
    """Find an instrument by its symbol (case-insensitive)."""
    sym = symbol.upper()
    for i in DEFAULT_INSTRUMENTS:
        if i.symbol.upper() == sym:
            return i
    return None
