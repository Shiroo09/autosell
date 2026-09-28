/* sahibinden.com mock - category tree, attribute definitions and address data */
(function (w) {
  'use strict';
  var L = null; /* leaf marker */

  var TREE = {
    'Emlak': {
      'Konut': {
        'Satılık': { 'Daire': L, 'Residence': L, 'Müstakil Ev': L, 'Villa': L },
        'Kiralık': { 'Daire': L, 'Residence': L, 'Müstakil Ev': L },
        'Turistik Günlük Kiralık': L
      },
      'İş Yeri': { 'Satılık': L, 'Kiralık': L, 'Devren Satılık': L },
      'Arsa': { 'Satılık': L, 'Kiralık': L },
      'Konut Projeleri': L,
      'Bina': L,
      'Devre Mülk': L,
      'Turistik Tesis': L
    },
    'Vasıta': {
      'Otomobil': {
        'Alfa Romeo': L,
        'Audi': L,
        'BMW': L,
        'Citroën': L,
        'Dacia': L,
        'Fiat': { 'Egea': L, 'Linea': L, 'Punto': L },
        'Ford': L,
        'Honda': L,
        'Hyundai': L,
        'Mercedes-Benz': L,
        'Opel': L,
        'Peugeot': L,
        'Renault': {
          'Clio': { '1.0 TCe Joy': L, '1.0 TCe Touch': L, '1.2 Joy': L, '1.5 dCi Joy': L, '1.5 dCi Touch': L, '1.3 TCe Icon': L },
          'Megane': { '1.3 TCe Joy': L, '1.5 dCi Touch': L, '1.6 Icon': L },
          'Symbol': L,
          'Taliant': L,
          'Fluence': L
        },
        'Toyota': { 'Corolla': L, 'C-HR': L, 'Yaris': L },
        'Volkswagen': { 'Golf': L, 'Passat': L, 'Polo': L }
      },
      'Arazi, SUV & Pickup': L,
      'Motosiklet': L,
      'Minivan & Panelvan': L,
      'Ticari Araçlar': L,
      'Elektrikli Araçlar': L,
      'Deniz Araçları': L,
      'Hasarlı Araçlar': L,
      'Karavan': L,
      'Klasik Araçlar': L,
      'Hava Araçları': L,
      'ATV': L,
      'UTV': L,
      'Engelli Plakalı Araçlar': L
    },
    'Yedek Parça, Aksesuar, Donanım & Tuning': {
      'Otomotiv Ekipmanları': L,
      'Motosiklet Ekipmanları': L,
      'Deniz Aracı Ekipmanları': L
    },
    'İkinci El ve Sıfır Alışveriş': {
      'Bilgisayar': {
        'Dizüstü (Notebook)': { 'Apple': L, 'Lenovo': L, 'Asus': L, 'HP': L, 'Acer': L, 'Dell': L, 'Monster': L, 'MSI': L },
        'Masaüstü': L,
        'Tablet': L,
        'Bilgisayar Bileşenleri': L,
        'Monitör': L,
        'Yazıcı & Tarayıcı': L
      },
      'Cep Telefonu': {
        'Modeller': {
          'Apple': {
            'iPhone 11': L, 'iPhone 11 Pro': L, 'iPhone 12': L, 'iPhone 12 mini': L, 'iPhone 12 Pro': L,
            'iPhone 13': L, 'iPhone 13 mini': L, 'iPhone 13 Pro': L, 'iPhone 13 Pro Max': L,
            'iPhone 14': L, 'iPhone 14 Plus': L, 'iPhone 14 Pro': L,
            'iPhone 15': L, 'iPhone 15 Pro': L, 'iPhone 16': L
          },
          'Samsung': { 'Galaxy S21': L, 'Galaxy S21 FE': L, 'Galaxy S22': L, 'Galaxy S23': L, 'Galaxy A34': L, 'Galaxy A54': L },
          'Xiaomi': { 'Redmi Note 12': L, 'Redmi Note 13': L, 'Xiaomi 13T': L },
          'Huawei': { 'P30 Lite': L, 'P40': L, 'Nova 9': L },
          'Oppo': L,
          'Diğer Markalar': L
        },
        'Aksesuarlar': { 'Kılıf': L, 'Şarj Cihazı': L, 'Kulaklık': L, 'Ekran Koruyucu': L },
        'Yedek Parça': L
      },
      'Fotoğraf & Kamera': L,
      'Ev Dekorasyon': {
        'Mobilya': { 'Koltuk Takımı': L, 'Yemek Odası': L, 'Yatak Odası': L, 'TV Ünitesi': L, 'Masa & Sandalye': L },
        'Aydınlatma': L,
        'Halı & Kilim': L
      },
      'Ev Elektroniği': { 'Televizyon': L, 'Ses Sistemleri': L },
      'Beyaz Eşya': { 'Buzdolabı': L, 'Çamaşır Makinesi': L, 'Bulaşık Makinesi': L },
      'Giyim & Aksesuar': L,
      'Saat': L,
      'Anne & Bebek': L,
      'Kişisel Bakım & Kozmetik': L,
      'Hobi & Oyuncak': L,
      'Oyun & Konsol': {
        'Konsollar': { 'PlayStation 5': L, 'PlayStation 4': L, 'Xbox Series X|S': L, 'Nintendo Switch': L },
        'Oyunlar': L,
        'Oyun Aksesuarları': L
      },
      'Kitap, Dergi & Film': L,
      'Müzik': L,
      'Spor': L,
      'Takı & Mücevher': L,
      'Koleksiyon': L,
      'Antika': L,
      'Bahçe & Yapı Market': L,
      'Teknik Elektronik': L,
      'Ofis & Kırtasiye': L,
      'Yiyecek & İçecek': L,
      'Diğer Her Şey': L
    },
    'İş Makineleri & Sanayi': { 'İş Makineleri': L, 'Tarım Makineleri': L, 'Sanayi': L, 'Elektrik & Enerji': L },
    'Ustalar ve Hizmetler': { 'Ev Tadilat & Dekorasyon': L, 'Nakliye': L, 'Araç Servis & Bakım': L, 'Temizlik': L },
    'Özel Ders Verenler': { 'Lise & Üniversite Hazırlık': L, 'İlkokul & Ortaokul': L, 'Yabancı Dil': L, 'Müzik & Enstrüman': L },
    'İş İlanları': { 'Satış & Pazarlama': L, 'Muhasebe & Finans': L, 'Eğitim': L, 'Bilişim': L },
    'Yardımcı Arayanlar': { 'Bebek & Çocuk Bakıcısı': L, 'Yaşlı & Hasta Bakıcısı': L, 'Temizlikçi & Ev İşlerine Yardımcı': L },
    'Hayvanlar Alemi': { 'Evcil Hayvanlar': { 'Kedi': L, 'Köpek': L, 'Kuş': L, 'Balık': L }, 'Akvaryum': L, 'Hayvan Aksesuarları': L }
  };

  var COLORS = ['Siyah', 'Beyaz', 'Gri', 'Gümüş', 'Altın', 'Mavi', 'Lacivert', 'Kırmızı', 'Yeşil', 'Mor', 'Pembe', 'Sarı', 'Turuncu', 'Kahverengi', 'Bej'];
  var YEARS = [];
  for (var y = 2026; y >= 1990; y--) { YEARS.push(String(y)); }

  /* labelFor:true -> <label for="...">, false -> label text in a sibling <div> (legacy markup) */
  var ATTRS = {
    phone: [
      { key: 'dahili_hafiza', label: 'Dahili Hafıza', type: 'select', required: true, labelFor: false, options: ['32 GB', '64 GB', '128 GB', '256 GB', '512 GB', '1 TB'] },
      { key: 'ram_bellek', label: 'RAM Bellek', type: 'select', required: false, labelFor: true, options: ['2 GB', '3 GB', '4 GB', '6 GB', '8 GB', '12 GB', '16 GB'] },
      { key: 'renk', label: 'Renk', type: 'select', required: true, labelFor: true, options: COLORS },
      { key: 'garanti', label: 'Garanti', type: 'radio', required: true, options: ['Evet', 'Hayır'] },
      { key: 'durumu', label: 'Durumu', type: 'select', required: true, labelFor: false, options: ['Sıfır', 'İkinci El', 'Yenilenmiş'] },
      { key: 'kimden', label: 'Kimden', type: 'radio', required: true, options: ['Sahibinden', 'Mağazadan'] },
      { key: 'takas', label: 'Takas', type: 'radio', required: true, options: ['Evet', 'Hayır'] }
    ],
    car: [
      { key: 'yil', label: 'Yıl', type: 'select', required: true, labelFor: false, options: YEARS },
      { key: 'yakit', label: 'Yakıt', type: 'select', required: true, labelFor: true, options: ['Benzin', 'Dizel', 'LPG & Benzin', 'Hibrit', 'Elektrik'] },
      { key: 'vites', label: 'Vites', type: 'select', required: true, labelFor: false, options: ['Manuel', 'Otomatik', 'Yarı Otomatik'] },
      { key: 'km', label: 'KM', type: 'text', required: true, labelFor: true, numeric: true },
      { key: 'kasa_tipi', label: 'Kasa Tipi', type: 'select', required: true, labelFor: false, options: ['Hatchback 5 kapı', 'Hatchback 3 kapı', 'Sedan', 'Station wagon', 'Coupe', 'Cabrio', 'MPV', 'SUV'] },
      { key: 'renk', label: 'Renk', type: 'select', required: true, labelFor: true, options: COLORS },
      { key: 'agir_hasar', label: 'Ağır Hasar Kayıtlı', type: 'radio', required: true, options: ['Evet', 'Hayır'] },
      { key: 'kimden', label: 'Kimden', type: 'radio', required: true, options: ['Sahibinden', 'Galeriden', 'Yetkili Bayiden'] },
      { key: 'takas', label: 'Takas', type: 'radio', required: true, options: ['Evet', 'Hayır'] }
    ],
    generic: [
      { key: 'durumu', label: 'Durumu', type: 'select', required: true, labelFor: false, options: ['Sıfır', 'İkinci El'] },
      { key: 'kimden', label: 'Kimden', type: 'radio', required: true, options: ['Sahibinden', 'Mağazadan'] },
      { key: 'takas', label: 'Takas', type: 'radio', required: true, options: ['Evet', 'Hayır'] }
    ]
  };

  function attrGroup(path) {
    if (path[0] === 'İkinci El ve Sıfır Alışveriş' && path[1] === 'Cep Telefonu' && path[2] === 'Modeller') { return 'phone'; }
    if (path[0] === 'Vasıta' && path[1] === 'Otomobil') { return 'car'; }
    return 'generic';
  }

  /* read-only info rows derived from the category (not part of "attributes") */
  function fixedInfo(path) {
    var g = attrGroup(path);
    var rows = [];
    if (g === 'phone') {
      if (path[3]) { rows.push(['Marka', path[3]]); }
      if (path[4]) { rows.push(['Model', path[4]]); }
    } else if (g === 'car') {
      if (path[2]) { rows.push(['Marka', path[2]]); }
      if (path[3]) { rows.push(['Seri', path[3]]); }
      if (path[4]) { rows.push(['Model', path[4]]); }
    }
    return rows;
  }

  function childrenOf(path) {
    var node = TREE;
    for (var i = 0; i < path.length; i++) {
      if (!node || !Object.prototype.hasOwnProperty.call(node, path[i])) { return undefined; }
      node = node[path[i]];
    }
    return node; /* object -> children, null -> leaf, undefined -> invalid */
  }

  function isLeafPath(path) { return path && path.length > 0 && childrenOf(path) === null; }

  var CITIES = ['Adana', 'Adıyaman', 'Afyonkarahisar', 'Ağrı', 'Aksaray', 'Amasya', 'Ankara', 'Antalya', 'Ardahan', 'Artvin',
    'Aydın', 'Balıkesir', 'Bartın', 'Batman', 'Bayburt', 'Bilecik', 'Bingöl', 'Bitlis', 'Bolu', 'Burdur', 'Bursa', 'Çanakkale',
    'Çankırı', 'Çorum', 'Denizli', 'Diyarbakır', 'Düzce', 'Edirne', 'Elazığ', 'Erzincan', 'Erzurum', 'Eskişehir', 'Gaziantep',
    'Giresun', 'Gümüşhane', 'Hakkari', 'Hatay', 'Iğdır', 'Isparta', 'İstanbul', 'İzmir', 'Kahramanmaraş', 'Karabük', 'Karaman',
    'Kars', 'Kastamonu', 'Kayseri', 'Kırıkkale', 'Kırklareli', 'Kırşehir', 'Kilis', 'Kocaeli', 'Konya', 'Kütahya', 'Malatya',
    'Manisa', 'Mardin', 'Mersin', 'Muğla', 'Muş', 'Nevşehir', 'Niğde', 'Ordu', 'Osmaniye', 'Rize', 'Sakarya', 'Samsun', 'Siirt',
    'Sinop', 'Sivas', 'Şanlıurfa', 'Şırnak', 'Tekirdağ', 'Tokat', 'Trabzon', 'Tunceli', 'Uşak', 'Van', 'Yalova', 'Yozgat', 'Zonguldak'];

  var DISTRICTS = {
    'İstanbul': {
      'Ataşehir': ['Atatürk Mah.', 'Barbaros Mah.', 'İçerenköy Mah.'],
      'Bakırköy': ['Ataköy 1. Kısım Mah.', 'Yeşilköy Mah.'],
      'Beşiktaş': ['Levent Mah.', 'Bebek Mah.', 'Etiler Mah.', 'Ortaköy Mah.'],
      'Kadıköy': ['Caferağa Mah.', 'Moda Mah.', 'Fenerbahçe Mah.', 'Göztepe Mah.', 'Koşuyolu Mah.'],
      'Kartal': ['Kordonboyu Mah.', 'Yakacık Mah.'],
      'Şişli': ['Mecidiyeköy Mah.', 'Nişantaşı Mah.'],
      'Üsküdar': ['Altunizade Mah.', 'Acıbadem Mah.', 'Kuzguncuk Mah.']
    },
    'Ankara': {
      'Çankaya': ['Kızılay Mah.', 'Bahçelievler Mah.', 'Ayrancı Mah.'],
      'Keçiören': ['Etlik Mah.', 'Kalaba Mah.'],
      'Yenimahalle': ['Batıkent Mah.', 'Demetevler Mah.']
    },
    'İzmir': {
      'Bornova': ['Kazımdirik Mah.', 'Erzene Mah.', 'Evka 3 Mah.'],
      'Karşıyaka': ['Bostanlı Mah.', 'Mavişehir Mah.', 'Alaybey Mah.'],
      'Konak': ['Alsancak Mah.', 'Güzelyalı Mah.']
    }
  };

  function districtsOf(city) {
    if (DISTRICTS[city]) { return Object.keys(DISTRICTS[city]); }
    return city ? ['Merkez'] : [];
  }
  function quartersOf(city, district) {
    if (DISTRICTS[city] && DISTRICTS[city][district]) { return DISTRICTS[city][district].slice(); }
    return district ? ['Cumhuriyet Mah.', 'Yenişehir Mah.'] : [];
  }

  w.SHB_DATA = {
    TREE: TREE,
    ATTRS: ATTRS,
    attrGroup: attrGroup,
    fixedInfo: fixedInfo,
    childrenOf: childrenOf,
    isLeafPath: isLeafPath,
    CITIES: CITIES,
    districtsOf: districtsOf,
    quartersOf: quartersOf
  };
})(window);
