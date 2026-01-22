import asyncio
import json
import re
from playwright.async_api import async_playwright
from urllib.parse import urljoin

class EmlakjetStrictScraper:
    def __init__(self):
        self.base_url = "https://www.emlakjet.com"
        self.firm_url = "https://www.emlakjet.com/emlak-ofisleri-detay/goktas-emlak-310758"
        
    async def create_stealth_context(self, playwright):
        browser = await playwright.chromium.launch(
            headless=False,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        return browser, context
    
    async def get_firm_listings(self):
        async with async_playwright() as playwright:
            browser, context = await self.create_stealth_context(playwright)
            page = await context.new_page()
            
            try:
                await page.goto(self.firm_url, wait_until='networkidle')
                await asyncio.sleep(3)
                
                listing_elements = await page.query_selector_all('a[href*="/ilan/"]')
                listings = []
                
                for element in listing_elements:
                    href = await element.get_attribute('href')
                    if href and '/ilan/' in href:
                        full_url = urljoin(self.base_url, href)
                        listing_id = re.search(r'-(\d+)$', full_url)
                        if listing_id and full_url not in [l.get('ilanUrl') for l in listings]:
                            listings.append({
                                'ilanUrl': full_url,
                                'ilanNo': listing_id.group(1)
                            })
                
                await browser.close()
                return listings
            except:
                await browser.close()
                return []
    
    async def get_listing_details(self, listing_url):
        async with async_playwright() as playwright:
            browser, context = await self.create_stealth_context(playwright)
            page = await context.new_page()
            
            try:
                await page.goto(listing_url, wait_until='networkidle')
                await asyncio.sleep(3)
                
                # Extract ALL data from #ilan-hakkinda
                details = await self.extract_all_ilan_data(page)
                details['ilanUrl'] = listing_url
                details['ilanNo'] = re.search(r'-(\d+)$', listing_url).group(1)
                
                await browser.close()
                return details
            except:
                await browser.close()
                return None
    
    async def extract_all_ilan_data(self, page):
        """Extract İlan Bilgileri, İlan Açıklaması, İlan Özellikleri, Fiyat"""
        try:
            # Check if container exists
            container = await page.query_selector('#ilan-hakkinda')
            if not container:
                return None
            
            result = {
                'ilan_bilgileri': {},
                'ilan_aciklamasi_html': None,
                'ilan_ozellikleri': {
                    'ic_ozellikler': {},
                    'dis_ozellikler': {},
                    'konum_ozellikleri': {}
                },
                'fiyat_bilgileri': {}
            }
            
            # 1) İlan Bilgileri
            await self.extract_ilan_bilgileri(container, result['ilan_bilgileri'])
            
            # 2) Fiyat Bilgileri
            await self.extract_fiyat_bilgileri(page, result['fiyat_bilgileri'])
            
            # 3) İlan Açıklaması
            await self.extract_ilan_aciklamasi(container, result)
            
            # 4) İlan Özellikleri
            await self.extract_ilan_ozellikleri(page, result['ilan_ozellikleri'])
            
            return result
        except Exception as e:
            print(f"Extraction error: {e}")
            return None
    
    async def extract_fiyat_bilgileri(self, page, fiyat_bilgileri):
        """Extract price information"""
        try:
            # Try multiple price selectors
            price_selectors = [
                'span.n-prop-detail-price',
                'div.price',
                'span.price',
                'div.fiyat',
                'span.fiyat',
                'div[class*="price"]',
                'span[class*="price"]',
                'div[class*="fiyat"]',
                'span[class*="fiyat"]'
            ]
            
            for selector in price_selectors:
                price_elem = await page.query_selector(selector)
                if price_elem:
                    price_text = await price_elem.inner_text()
                    if price_text and price_text.strip():
                        fiyat_bilgileri['fiyat_text'] = price_text.strip()
                        
                        # Extract numeric value
                        import re
                        price_match = re.search(r'[\d.]+', price_text.replace('.', ''))
                        if price_match:
                            fiyat_bilgileri['fiyat'] = int(price_match.group().replace('.', ''))
                        
                        # Extract currency
                        if 'TL' in price_text or '₺' in price_text:
                            fiyat_bilgileri['para_birimi'] = 'TL'
                        elif '$' in price_text:
                            fiyat_bilgileri['para_birimi'] = 'USD'
                        elif '€' in price_text:
                            fiyat_bilgileri['para_birimi'] = 'EUR'
                        
                        return
            
            # Try to find price in page title or meta tags
            title = await page.title()
            if title:
                import re
                price_match = re.search(r'([\d.]+)\s*(?:TL|₺|\$|€)', title)
                if price_match:
                    fiyat_bilgileri['fiyat_text'] = price_match.group(0)
                    fiyat_bilgileri['fiyat'] = int(price_match.group(1).replace('.', ''))
                    if 'TL' in price_match.group(0) or '₺' in price_match.group(0):
                        fiyat_bilgileri['para_birimi'] = 'TL'
            
            # If still no price, check if it's mentioned in description
            if not fiyat_bilgileri.get('fiyat'):
                fiyat_bilgileri['fiyat'] = None
                fiyat_bilgileri['not'] = 'Fiyat bilgisi bulunamadı'
                
        except Exception as e:
            print(f"Fiyat extraction error: {e}")
            fiyat_bilgileri['fiyat'] = None
            fiyat_bilgileri['not'] = f'Extraction error: {e}'
    
    async def extract_ilan_bilgileri(self, container, bilgiler):
        """Extract key-value pairs from İlan Bilgileri"""
        try:
            list_items = await container.query_selector_all('ul > li')
            
            for item in list_items:
                key_span = await item.query_selector('span.styles_key__wX_g4')
                value_span = await item.query_selector('span.styles_value__xmNV3')
                
                if key_span and value_span:
                    key_text = await key_span.inner_text()
                    value_text = await value_span.inner_text()
                    
                    field_name = self.map_key_to_field(key_text.strip())
                    if field_name:
                        bilgiler[field_name] = value_text.strip()
        except:
            pass
    
    async def extract_ilan_aciklamasi(self, container, result):
        """Extract İlan Açıklaması HTML"""
        try:
            # Find the section with "İlan Açıklaması" heading
            aciklama_section = await container.query_selector('xpath=.//h2[contains(text(), "İlan Açıklaması")]/following-sibling::div//div[contains(@class, "styles_inner")]')
            if aciklama_section:
                result['ilan_aciklamasi_html'] = await aciklama_section.inner_html()
        except:
            pass
    
    async def extract_ilan_ozellikleri(self, page, ozellikler):
        """Extract İlan Özellikleri (İç/Dış/Konum)"""
        try:
            # Find the section with "İlan Özellikleri" - try multiple selectors
            ozellikler_section = await page.query_selector('#ilan-hakkinda h2:has-text("İlan Özellikleri")')
            if not ozellikler_section:
                # Try alternative selector
                ozellikler_section = await page.query_selector('xpath=.//h2[contains(text(), "İlan Özellikleri")]')
            if not ozellikler_section:
                print("İlan Özellikleri section bulunamadı")
                return
            
            # Get the parent section
            parent_section = await ozellikler_section.query_selector('xpath=./..')
            if not parent_section:
                return
            
            # Extract İç Özellikler (default selected)
            await self.extract_tab_ozellikleri(parent_section, 'ic_ozellikler', ozellikler['ic_ozellikler'])
            
            # Extract Dış Özellikler
            await self.click_and_extract_tab(parent_section, 'Dış Özellikler', 'dis_ozellikler', ozellikler['dis_ozellikler'])
            
            # Extract Konum Özellikleri
            await self.click_and_extract_tab(parent_section, 'Konum Özellikleri', 'konum_ozellikleri', ozellikler['konum_ozellikleri'])
            
        except Exception as e:
            print(f"Özellikler extraction error: {e}")
    
    async def extract_tab_ozellikleri(self, section, tab_name, target_dict):
        """Extract features from currently active tab"""
        try:
            # Find active tab content
            active_tab = await section.query_selector('div[role="tabpanel"][data-headlessui-state="selected"]')
            if not active_tab:
                # Try alternative selector for active tab
                active_tab = await section.query_selector('div[role="tabpanel"]')
            if not active_tab:
                print(f"Active tab bulunamadı: {tab_name}")
                return
            
            # Extract categories and features
            categories = await active_tab.query_selector_all('div.styles_tabContentTitle__3Q2jN')
            
            for category in categories:
                category_name = await category.inner_text()
                category_name = category_name.strip()
                
                # Find the feature list after this category
                feature_list = await category.query_selector('xpath=./following-sibling::ul[contains(@class, "tabContentList")]')
                if not feature_list:
                    # Try alternative selector
                    feature_list = await category.query_selector('xpath=./following-sibling::ul')
                if feature_list:
                    features = []
                    feature_items = await feature_list.query_selector_all('li')
                    
                    for item in feature_items:
                        feature_text = await item.inner_text()
                        features.append(feature_text.strip())
                    
                    if features:
                        target_dict[category_name] = features
        except Exception as e:
            print(f"Tab extraction error ({tab_name}): {e}")
    
    async def click_and_extract_tab(self, section, tab_text, tab_key, target_dict):
        """Click a tab and extract its features"""
        try:
            # Find and click the tab
            tab_button = await section.query_selector(f'button:has-text("{tab_text}")')
            if not tab_button:
                # Try alternative selector
                tab_button = await section.query_selector(f'xpath=.//button[contains(text(), "{tab_text}")]')
            if tab_button:
                await tab_button.click()
                await asyncio.sleep(2)  # Wait for content to load
                
                # Extract from newly activated tab
                await self.extract_tab_ozellikleri(section, tab_key, target_dict)
            else:
                print(f"Tab button bulunamadı: {tab_text}")
        except Exception as e:
            print(f"Tab click error ({tab_text}): {e}")
    
    def map_key_to_field(self, key_text):
        mapping = {
            'İlan Numarası': 'ilan_numarasi',
            'İlan Güncelleme Tarihi': 'ilan_guncelleme_tarihi',
            'Türü': 'turu',
            'Kategorisi': 'kategorisi',
            'Tipi': 'tipi',
            'Net Metrekare': 'net_metrekare',
            'Brüt Metrekare': 'brut_metrekare',
            'Oda Sayısı': 'oda_sayisi',
            'Binanın Yaşı': 'bina_yasi',
            'Bulunduğu Kat': 'bulundugu_kat',
            'Binanın Kat Sayısı': 'toplam_kat_sayisi',
            'Isıtma Tipi': 'isitma_tipi',
            'Kullanım Durumu': 'kullanim_durumu',
            'Krediye Uygunluk': 'krediye_uygunluk',
            'Tapu Durumu': 'tapu_durumu',
            'Site İçerisinde': 'site_icerisinde',
            'Banyo Sayısı': 'banyo_sayisi',
            'Fiyat Durumu': 'fiyat_durumu'
        }
        return mapping.get(key_text)
    
    async def scrape_all_listings(self):
        print("Emlakjet Strict scraping başlatılıyor...")
        
        listings = await self.get_firm_listings()
        
        if not listings:
            print("Hiç ilan bulunamadı!")
            return []
        
        print(f"Toplam {len(listings)} ilan detayları alınıyor...")
        
        detailed_listings = []
        for i, listing in enumerate(listings):
            print(f"[{i+1}/{len(listings)}] İlan: {listing['ilanNo']}")
            details = await self.get_listing_details(listing['ilanUrl'])
            if details:
                detailed_listings.append(details)
            
            await asyncio.sleep(2)
        
        return detailed_listings

async def main():
    scraper = EmlakjetStrictScraper()
    listings = await scraper.scrape_all_listings()
    
    with open('emlakjet_listings_raw.json', 'w', encoding='utf-8') as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)
    
    print(f"Toplam {len(listings)} ilan başarıyla çekildi ve kaydedildi.")

if __name__ == "__main__":
    asyncio.run(main())
