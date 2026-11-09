"""The fictional world: one brand, three markets, a trilingual catalogue.

"Lune & Lin" is an invented French brand of linen stationery, tea and home goods that sells
online in France, Japan and Taiwan. Every name, product and price here is made up.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

BRAND = {"fr": "Lune & Lin", "ja": "リュヌ・エ・ラン", "zh-Hant": "月與亞麻", "en": "Lune & Lin"}

# Fixed exchange rates: an assumption for the simulation, not market data.
FX_FROM_EUR = {"EUR": 1.0, "JPY": 160.0, "TWD": 35.0}
# Cross-border price positioning (duties, shipping, brand premium), also an assumption.
CROSS_BORDER_MARKUP = {"FR": 1.0, "JP": 1.15, "TW": 1.10}


@dataclass(frozen=True)
class Market:
    code: str
    country_en: str
    currency: str
    language: str
    timezone: str
    faker_locale: str
    channels: tuple[str, ...]
    email_domain: str


MARKETS: dict[str, Market] = {
    "FR": Market("FR", "France", "EUR", "fr", "Europe/Paris", "fr_FR", ("email",), "example.com"),
    "JP": Market("JP", "Japan", "JPY", "ja", "Asia/Tokyo", "ja_JP", ("email", "line"), "example.com"),
    "TW": Market("TW", "Taiwan", "TWD", "zh-Hant", "Asia/Taipei", "zh_TW", ("line", "email"), "example.org"),
}

CATEGORIES = {
    "stationery": {"fr": "Papeterie", "ja": "文房具", "zh-Hant": "文具", "en": "Stationery"},
    "tea": {"fr": "Thé et épicerie fine", "ja": "紅茶・食品", "zh-Hant": "茶與精選食品", "en": "Tea and fine food"},
    "home": {"fr": "Maison et parfum", "ja": "ホームフレグランス", "zh-Hant": "居家香氛", "en": "Home fragrance"},
    "books": {"fr": "Livres et BD", "ja": "本・バンド・デシネ", "zh-Hant": "書籍與法式漫畫", "en": "Books and comics"},
    "table": {"fr": "Art de la table", "ja": "テーブルウェア", "zh-Hant": "餐桌器皿", "en": "Tableware"},
}

# Relative appetite for each category by market (assumption; shapes the baskets).
CATEGORY_WEIGHTS = {
    "FR": {"stationery": 1.0, "tea": 0.8, "home": 1.0, "books": 1.4, "table": 1.2},
    "JP": {"stationery": 1.6, "tea": 1.3, "home": 0.9, "books": 0.7, "table": 1.0},
    "TW": {"stationery": 1.0, "tea": 1.6, "home": 1.3, "books": 0.8, "table": 0.9},
}

_COLOURS = [
    ("Bleu de Provence", "プロヴァンスブルー", "普羅旺斯藍"),
    ("Vert sauge", "セージグリーン", "鼠尾草綠"),
    ("Rose poudré", "パウダーピンク", "粉霧玫瑰"),
    ("Gris lin", "リネングレー", "亞麻灰"),
    ("Jaune mimosa", "ミモザイエロー", "含羞草黃"),
]
_FLAVOURS = [
    ("Pêche blanche", "白桃", "白桃"),
    ("Cassis", "カシス", "黑醋栗"),
    ("Abricot", "アプリコット", "杏桃"),
    ("Framboise", "フランボワーズ", "覆盆子"),
    ("Bergamote", "ベルガモット", "佛手柑"),
]
_SCENTS = [
    ("Figue", "フィグ", "無花果"),
    ("Lavande", "ラベンダー", "薰衣草"),
    ("Fleur d'oranger", "オレンジフラワー", "橙花"),
    ("Cèdre", "シダー", "雪松"),
    ("Thé blanc", "ホワイトティー", "白茶"),
]
_VOLUMES = [(f"Tome {i}", f"第{i}巻", f"第{i}集") for i in range(1, 6)]

# (code, category, fr, ja, zh-Hant, price in EUR, variant family)
_BASES = [
    ("NB", "stationery", "Carnet en lin A5", "リネンノート A5", "亞麻筆記本 A5", 16.0, _COLOURS),
    ("FP", "stationery", "Stylo plume", "万年筆", "鋼筆", 38.0, _COLOURS),
    ("PC", "stationery", "Coffret de cartes postales", "ポストカードセット", "明信片組", 12.0, _COLOURS),
    ("TE", "tea", "Thé noir aux fruits", "フルーツ紅茶", "水果紅茶", 14.0, _FLAVOURS),
    ("BI", "tea", "Coffret de biscuits au beurre", "バタービスケット缶", "奶油餅乾禮盒", 18.0, _FLAVOURS),
    ("JA", "tea", "Confiture artisanale", "手作りジャム", "手工果醬", 9.0, _FLAVOURS),
    ("CA", "home", "Bougie parfumée", "アロマキャンドル", "香氛蠟燭", 26.0, _SCENTS),
    ("DI", "home", "Diffuseur de parfum", "リードディフューザー", "擴香瓶", 32.0, _SCENTS),
    ("BD", "books", "Bande dessinée, édition traduite", "バンド・デシネ（翻訳版）", "法式漫畫（中譯本）", 22.0, _VOLUMES),
    ("CB", "books", "Livre de recettes illustré", "イラストレシピ本", "插畫食譜", 28.0, _VOLUMES),
    ("MU", "table", "Tasse en céramique", "陶器マグカップ", "陶瓷馬克杯", 19.0, _COLOURS),
    ("TO", "table", "Torchon en lin", "リネンキッチンクロス", "亞麻茶巾", 15.0, _COLOURS),
]


def local_price(price_eur: float, currency: str, market: str) -> float:
    """Price as a shop in that country would display it.

    Japan: up to the next hundred minus 20 yen (2,980 yen style). Taiwan: up to the next
    hundred minus 10 (NT$590 style). France: whole euros with a .90 ending.
    """
    raw = price_eur * FX_FROM_EUR[currency] * CROSS_BORDER_MARKUP[market]
    if currency == "JPY":
        return float(math.ceil(raw / 100) * 100 - 20)
    if currency == "TWD":
        return float(math.ceil(raw / 100) * 100 - 10)
    return math.floor(raw) + 0.90


@dataclass(frozen=True)
class Product:
    product_id: int
    sku: str
    category: str
    name_fr: str
    name_ja: str
    name_zh_hant: str
    price_eur: float
    price_jpy: float
    price_twd: float

    def price(self, currency: str) -> float:
        return {"EUR": self.price_eur, "JPY": self.price_jpy, "TWD": self.price_twd}[currency]

    def name(self, language: str) -> str:
        return {"fr": self.name_fr, "ja": self.name_ja, "zh-Hant": self.name_zh_hant}[language]


def catalogue() -> list[Product]:
    products, pid = [], 1000
    for code, cat, fr, ja, zh, eur, variants in _BASES:
        for i, (vfr, vja, vzh) in enumerate(variants, start=1):
            pid += 1
            products.append(Product(
                product_id=pid,
                sku=f"LL-{code}-{i:02d}",
                category=cat,
                name_fr=f"{fr} · {vfr}",
                name_ja=f"{ja}・{vja}",
                name_zh_hant=f"{zh}・{vzh}",
                price_eur=local_price(eur, "EUR", "FR"),
                price_jpy=local_price(eur, "JPY", "JP"),
                price_twd=local_price(eur, "TWD", "TW"),
            ))
    return products
