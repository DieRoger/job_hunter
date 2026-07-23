"""
拉勾网平台适配器
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from loguru import logger

from src.agents.search_agent import BasePlatformAdapter
from src.config import crawler_config
from src.models.schemas import JobDescription


class LagouAdapter(BasePlatformAdapter):
    """拉勾网适配器"""

    platform = "lagou"

    def __init__(self):
        cfg = crawler_config.platforms.get("lagou")
        self._base_url = cfg.base_url if cfg else "https://www.lagou.com"
        self._interval_range = cfg.request_interval if cfg else [5, 10]
        self._browser = None
        self._playwright = None

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
        """搜索拉勾职位"""
        await self._ensure_browser()
        await self._random_delay()

        page = await self._browser.new_page()
        try:
            # 拉勾搜索 URL
            encoded_keyword = keyword
            search_url = f"{self._base_url}/wn/jobs?kd={encoded_keyword}&city={city}"
            await page.goto(search_url, wait_until="networkidle", timeout=30000)
            await self._random_delay()

            # 等待职位列表加载
            await page.wait_for_selector(".job-list-box .job-card-wrapper", timeout=10000)

            # 提取职位列表
            job_cards = await page.query_selector_all(".job-card-wrapper")
            jobs = []

            for card in job_cards[:top_n]:
                try:
                    title_el = await card.query_selector(".job-name")
                    company_el = await card.query_selector(".company-name")
                    salary_el = await card.query_selector(".salary")
                    exp_el = await card.query_selector(".experience")
                    edu_el = await card.query_selector(".education")

                    title = (await title_el.inner_text()).strip() if title_el else ""
                    company = (await company_el.inner_text()).strip() if company_el else ""
                    salary = (await salary_el.inner_text()).strip() if salary_el else ""
                    experience = (await exp_el.inner_text()).strip() if exp_el else ""
                    education = (await edu_el.inner_text()).strip() if edu_el else ""

                    # 点击进入详情页获取更多信息
                    job_link = await card.query_selector("a")
                    detail_url = ""
                    if job_link:
                        detail_url = await job_link.get_attribute("href") or ""

                    jd = JobDescription(
                        title=title,
                        company=company,
                        salary=salary,
                        city=city,
                        education=education,
                        experience_years=self._parse_years(experience),
                        source_platform="lagou",
                        source_url=detail_url or search_url,
                    )
                    jobs.append(jd)
                except Exception as e:
                    logger.debug(f"拉勾解析卡片失败: {e}")
                    continue

            logger.info(f"拉勾搜索完成: {keyword} → {len(jobs)} 个职位")
            return jobs
        except Exception as e:
            logger.error(f"拉勾搜索失败: {e}")
            return []
        finally:
            await page.close()

    async def parse_job(self, job_id: str) -> JobDescription:
        """解析拉勾职位详情页"""
        await self._ensure_browser()
        await self._random_delay()

        page = await self._browser.new_page()
        try:
            await page.goto(job_id, wait_until="networkidle", timeout=30000)
            await self._random_delay()

            # 提取详情
            title_el = await page.query_selector(".job-name .name")
            company_el = await page.query_selector(".company")
            desc_el = await page.query_selector(".job-detail")
            skills_el = await page.query_selector_all(".job-tags .tag-item")

            title = (await title_el.inner_text()).strip() if title_el else ""
            company = (await company_el.inner_text()).strip() if company_el else ""
            description = (await desc_el.inner_text()).strip() if desc_el else ""
            skills = []
            for tag in (skills_el or []):
                text = (await tag.inner_text()).strip()
                if text:
                    skills.append(text)

            salary_el = await page.query_selector(".job_request .salary")
            salary = (await salary_el.inner_text()).strip() if salary_el else ""

            return JobDescription(
                id=job_id,
                title=title,
                company=company,
                salary=salary,
                description=description,
                skills_required=skills,
                source_platform="lagou",
                source_url=job_id,
                raw_text=description,
            )
        finally:
            await page.close()

    async def login(self) -> bool:
        """拉勾登录（暂不支持，返回 True 使用未登录搜索）"""
        logger.info("拉勾使用游客模式搜索")
        return True

    def _parse_years(self, exp_text: str) -> int:
        """解析经验年限文本"""
        exp_text = exp_text.lower().strip()
        if "不限" in exp_text or not exp_text:
            return 0
        if "应届" in exp_text:
            return 0
        # 提取数字
        import re
        match = re.search(r'(\d+)', exp_text)
        if match:
            return int(match.group(1))
        return 0

    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
