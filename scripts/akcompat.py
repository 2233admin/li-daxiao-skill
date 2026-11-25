"""akshare 版本兼容：脚本统一 `from akcompat import ak`，老函数名在新旧版本上都能用。

akshare 1.20.41–1.20.46 改了一批函数名（旧名直接抛 AttributeError）。本 skill 里用到的 9 个，
2026-11-26 在 1.18.94 与 1.20.70 上逐个比对过返回列，除 forex（两边都被东财限流，未比对）外完全一致，
所以这里只做改名映射，不改调用点。
"""

import akshare as ak

# 旧名 -> 新名
RENAMED = {
    'stock_zh_index_daily': 'index_zh_daily_sina',
    'stock_zh_index_spot_sina': 'index_zh_spot_sina',
    'stock_zh_index_value_csindex': 'index_value_csindex',
    'stock_hk_index_daily_sina': 'index_hk_daily_sina',
    'index_us_stock_sina': 'index_us_daily_sina',
    'futures_foreign_hist': 'futures_foreign_hist_sina',
    'forex_hist_em': 'fx_hist_em',
    'bond_zh_us_rate': 'bond_zh_us_yield_em',
    'stock_zh_a_spot': 'stock_zh_a_spot_sina',
}


def _has(name):
    try:
        getattr(ak, name)
        return True
    except AttributeError:
        return False


for _old, _new in RENAMED.items():
    if not _has(_old) and _has(_new):
        setattr(ak, _old, getattr(ak, _new))

__all__ = ['ak']
