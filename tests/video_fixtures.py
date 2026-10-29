from src.video.catalog import Catalog


def brief(**changes):
    return {
        "topic": "介绍字幕编辑功能",
        "audience": "首次制作短视频的创作者",
        "platform": "短视频平台",
        "duration_seconds": 30,
        "style": "简洁直观",
        "product_id": "P01",
        **changes,
    }


def draft():
    return {
        "title": "功能小演示",
        "scenes": [
            {
                "id": "S1",
                "visual": "screen_demo",
                "narration": "支持生成字幕草稿",
                "subtitle": "支持生成字幕草稿",
                "hold_seconds": 2,
                "fact_ids": ["M01:F1"],
            }
        ],
    }


def catalog():
    return Catalog.load()
