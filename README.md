# la-cuisine-des-mousquetaires
Collect data about the episodes of the show "La Cuisine des mousquetaires"

## Usage

### Scrape the INA
The scraping is carried out politely, with one request per second.
```shell
python ina_scraper.py 
```

### Check the score of the pairing:
```shell
cd src/la-cuisine-des-mousquetaires
python match_youtube.py --db ina_catalogue.sqlite --report
```