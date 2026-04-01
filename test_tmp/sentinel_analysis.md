## Analiza zdjęć satelitarnych Sentinel-2

### Cel analizy
Ocena aktywności biologicznej drzewostanu sosnowego w obszarze 1000 m wokół punktu N52.836980, E16.252285, z uwzględnieniem kondycji drzewostanu i reakcji na stres wodny (suszę).

### Zakres czasowy
Dane z okresu od 2018 roku do chwili obecnej.

### Selekcja wskaźników
Wykorzystanie repozytorium [awesome-spectral-indices](https://github.com/awesome-spectral-indices/awesome-spectral-indices) oraz biblioteki [eemont](https://github.com/davemlz/eemont) dla Google Earth Engine.

### Wskaźniki do analizy
- **NDVI (Normalized Difference Vegetation Index)**: Ocena biomasy roślinnej.
- **NDWI (Normalized Difference Water Index)**: Ocena zawartości wody w roślinach.
- **EVI (Enhanced Vegetation Index)**: Alternatywa dla NDVI, lepsza w warunkach zacienienia.
- **NDSI (Normalized Difference Snow Index)**: Ocena pokrywy śnieżnej (opcjonalnie).
- **TSAVI (Two-Trees SAVI)**: Ocena stanu zdrowia roślinności.
- **NDVI_NDWI**: Analiza korelacji między NDVI a NDWI.

### Przygotowanie danych
1. Pobranie danych Sentinel-2 dla wybranego obszaru i okresu.
2. Przetworzenie danych w Google Earth Engine.
3. Obliczenie wybranych wskaźników.

### Wizualizacja
Dodanie obszaru zainteresowania (AOI) na mapie jako przezroczystego okręgu z zaznaczonym środkiem.

### Kod w JavaScript dla Google Earth Engine
Poniżej znajduje się przykładowy kod do analizy:

```javascript

// Definicja obszaru zainteresowania
var aoi = ee.Geometry.Point([16.252285, 52.836980]).buffer(1000);

// Import biblioteki eemont
var eemont = require('users/davemlz/eemont:latest');

// Pobranie danych Sentinel-2
var sentinel2 = ee.ImageCollection('COPERNICUS/S2')
  .filterDate('2018-01-01', 'present')
  .filterBounds(aoi);

// Obliczenie wskaźników
var ndvi = sentinel2.map(function(image) {
  return ee.Algorithms.Landsat.NDVI(image.select(['B4', 'B3']));
});

var ndwi = sentinel2.map(function(image) {
  return ee.Algorithms.Landsat.NDWI(image.select(['B4', 'B3']));
});

// Dodanie obrazów do kompozycji
var composite = ee.Algorithms.Landsat.composite(sentinel2, {'tiled': true});

// Wizualizacja
Map.addLayer(composite, {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 0.3}, 'Sentinel-2');
Map.addLayer(aoi, {color: 'red'}, 'AOI');

// Analiza danych
// ... (dalsza analiza wskaźników)

```

### Uwagi
- Dostosuj kod do konkretnych potrzeb analizy.
- Rozważ dodatkowe wskaźniki z repozytorium awesome-spectral-indices.

### Źródła
- [awesome-spectral-indices](https://github.com/awesome-spectral-indices/awesome-spectral-indices)
- [eemont](https://github.com/davemlz/eemont)
