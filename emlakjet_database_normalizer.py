import json
import re

class EmlakjetDatabaseNormalizer:
    def __init__(self):
        self.normalized_listings = []
    
    def normalize_listings(self, raw_file_path):
        """Normalize raw Emlakjet listings to database schema"""
        try:
            with open(raw_file_path, 'r', encoding='utf-8') as f:
                raw_listings = json.load(f)
            
            for listing in raw_listings:
                normalized = self.normalize_single_listing(listing)
                self.normalized_listings.append(normalized)
            
            return self.normalized_listings
        except Exception as e:
            print(f"Normalization error: {e}")
            return []
    
    def normalize_single_listing(self, raw_listing):
        """Normalize single listing to database schema"""
        # Get raw data
        ilan_bilgileri = raw_listing.get('ilan_bilgileri', {})
        fiyat_bilgileri = raw_listing.get('fiyat_bilgileri', {})
        ozellikler = raw_listing.get('ilan_ozellikleri', {})
        
        normalized = {
            'ilanUrl': raw_listing.get('ilanUrl'),
            'ilanNo': raw_listing.get('ilanNo'),
            'm2Net': self.extract_number(ilan_bilgileri.get('net_metrekare')),
            'm2Brut': self.extract_number(ilan_bilgileri.get('brut_metrekare')),
            'odaSayisi': self.normalize_oda_sayisi(ilan_bilgileri.get('oda_sayisi')),
            'bulunduguKat': self.normalize_bulundugu_kat(ilan_bilgileri.get('bulundugu_kat')),
            'toplamKatSayisi': self.cast_int(ilan_bilgileri.get('toplam_kat_sayisi')),
            'binaYasi': self.normalize_bina_yasi(ilan_bilgileri.get('bina_yasi')),
            'ilanDurumu': self.normalize_ilan_durumu(ilan_bilgileri.get('kategorisi')),
            'isitmaSistemi': self.normalize_isitma_tipi(ilan_bilgileri.get('isitma_tipi')),
            'siteIcerisinde': self.normalize_boolean(ilan_bilgileri.get('site_icerisinde')),
            'fiyat': fiyat_bilgileri.get('fiyat'),
            'ilanAciklamasiHtml': raw_listing.get('ilan_aciklamasi_html'),
            'ozellikler': self.normalize_ozellikler(ozellikler)
        }
        
        return normalized
    
    def extract_number(self, text):
        """Extract only number from text"""
        if not text:
            return None
        
        # Remove "m²", spaces, text, keep only numbers
        cleaned = re.sub(r'[^\d]', '', str(text))
        return int(cleaned) if cleaned else None
    
    def normalize_oda_sayisi(self, text):
        """Normalize oda sayisi - keep as string"""
        if not text:
            return None
        
        return str(text).strip()
    
    def normalize_bulundugu_kat(self, text):
        """Normalize bulundugu kat - get only floor number"""
        if not text:
            return None
        
        # Extract just the floor number from "4.Kat", "9.Kat"
        match = re.search(r'(\d+)', str(text))
        return int(match.group(1)) if match else None
    
    def cast_int(self, value):
        """Cast to int"""
        if value is None:
            return None
        
        try:
            return int(value)
        except:
            return None
    
    def normalize_bina_yasi(self, text):
        """Normalize bina yasi - get first number"""
        if not text:
            return None
        
        # "0 (Yeni)" → 0, "11-15" → 11
        match = re.search(r'(\d+)', str(text))
        return int(match.group(1)) if match else None
    
    def normalize_ilan_durumu(self, text):
        """Normalize ilan durumu - lowercase and trim"""
        if not text:
            return None
        
        return str(text).lower().strip()
    
    def normalize_isitma_tipi(self, text):
        """Normalize isitma tipi - remove parentheses"""
        if not text:
            return None
        
        # Remove parentheses content
        cleaned = re.sub(r'\s*\([^)]*\)', '', str(text))
        return cleaned.strip()
    
    def normalize_boolean(self, text):
        """Normalize boolean fields"""
        if not text:
            return None
        
        text = str(text).lower().strip()
        return True if text == 'evet' else False if text == 'hayır' else None
    
    def normalize_ozellikler(self, ozellikler):
        """Normalize ozellikler - snake_case categories"""
        if not ozellikler:
            return {
                'ic': None,
                'dis': None,
                'konum': None
            }
        
        result = {}
        
        # İç özellikler
        ic_ozellikler = ozellikler.get('ic_ozellikler', {})
        result['ic'] = self.normalize_ozellik_group(ic_ozellikler)
        
        # Dış özellikler
        dis_ozellikler = ozellikler.get('dis_ozellikler', {})
        result['dis'] = self.normalize_ozellik_group(dis_ozellikler)
        
        # Konum özellikleri
        konum_ozellikleri = ozellikler.get('konum_ozellikleri', {})
        result['konum'] = self.normalize_ozellik_group(konum_ozellikleri)
        
        return result
    
    def normalize_ozellik_group(self, ozellik_group):
        """Normalize özellik group - snake_case categories"""
        if not ozellik_group:
            return None
        
        result = {}
        for category, features in ozellik_group.items():
            if not features or not isinstance(features, list):
                continue
            
            # Convert category name to snake_case
            snake_category = self.to_snake_case(category)
            result[snake_category] = features
        
        return result if result else None
    
    def to_snake_case(self, text):
        """Convert text to snake_case"""
        if not text:
            return None
        
        # Turkish character mapping
        tr_map = {
            'ı': 'i', 'İ': 'I', 'ğ': 'g', 'Ğ': 'G',
            'ü': 'u', 'Ü': 'U', 'ş': 's', 'Ş': 'S',
            'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'
        }
        
        # Replace Turkish characters
        for tr_char, en_char in tr_map.items():
            text = text.replace(tr_char, en_char)
        
        # Convert to snake_case
        snake = re.sub(r'[^a-zA-Z0-9]+', '_', str(text))
        return snake.lower().strip('_')
    
    def save_normalized(self, output_file):
        """Save normalized listings"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.normalized_listings, f, ensure_ascii=False, indent=2)
        
        print(f"Database normalized listings saved to: {output_file}")
        print(f"Total listings: {len(self.normalized_listings)}")

def main():
    normalizer = EmlakjetDatabaseNormalizer()
    
    # Normalize raw listings to database schema
    normalized_listings = normalizer.normalize_listings('emlakjet_listings_raw.json')
    
    # Save normalized listings
    normalizer.save_normalized('emlakjet_listings_database.json')
    
    # Print sample
    if normalized_listings:
        print("\nSample database normalized listing:")
        print(json.dumps(normalized_listings[0], ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
