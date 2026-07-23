"""
BOSS直聘平台适配器
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from loguru import logger

from src.agents.search_agent import BasePlatformAdapter
from src.config import crawler_config
from src.models.schemas import JobDescription


class BossAdapter(BasePlatformAdapter):
    """BOSS直聘适配器"""

    platform = "boss"

    def __init__(self):
        cfg = crawler_config.platforms.get("boss")
        self._base_url = cfg.base_url if cfg else "https://www.zhipin.com"
        self._interval_range = cfg.request_interval if cfg else [3, 8]
        self._browser = None
        self._context = None

    async def _ensure_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )

    async def _random_delay(self):
        delay = random.uniform(*self._interval_range)
        await asyncio.sleep(delay)

    async def search(self, keyword: str, city: str = "北京", top_n: int = 10) -> list[JobDescription]:
        """搜索职位"""
        await self._ensure_browser()
        await self._random_delay()

        page = await self._browser.new_page()
        try:
            # BOSS直聘搜索 URL
            search_url = f"{self._base_url}/web/geek/job?query={keyword}&city={city}"
            await page.goto(search_url, wait_until="networkidle", timeout=30000)
            await self._random_delay()

            # 提取职位列表
            job_cards = await page.query_selector_all(".job-card-wrapper")
            jobs = []

            for card in job_cards[:top_n]:
                try:
                    title_el = await card.query_selector(".job-name")
                    company_el = await card.query_selector(".company-name")
                    salary_el = await card.query_selector(".salary")

                    title = await title_el.inner_text() if title_el else ""
                    company = await company_el.inner_text() if company_el else ""
                    salary = await salary_el.inner_text() if salary_el else ""

                    jobs.append(JobDescription(
                        title=title.strip(),
                        company=company.strip(),
                        salary=salary.strip(),
                        city=city,
                        source_platform="boss",
                    ))
                except Exception as e:
                    logger.debug(f"解析职位卡片失败: {e}")
                    continue

            logger.info(f"BOSS直聘搜索完成: {keyword} → {len(jobs)} 个职位")
            return jobs
        finally:
            await page.close()

    async def parse_job(self, job_id: str) -> JobDescription:
        """解析单个职位详情"""
        return JobDescription(id=job_id, source_platform="boss")
