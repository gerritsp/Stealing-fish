"""Download Minnesota DNR survey inventory for lakes in Data/processed/bwca_lakes.parquet.

Requirements: pip install pandas pyarrow requests
Run from the project root: python download_bwca_dnr_surveys.py
"""
from pathlib import Path
import time

import pandas as pd
import requests

LAKES_PATH = Path('bwca_lakes.parquet')
OUTPUT = Path('fisheries')
BASE = ('https://enterprise.gisdata.mn.gov/aghost/rest/services/'
        'us_mn_state_dnr/env_lakes_surveyed_by_mndnr/MapServer')

session = requests.Session()
session.headers['User-Agent'] = 'BWCA-site-finder/1.0 (public DNR ArcGIS data download)'


def normalized_dow(value):
    if pd.isna(value):
        return None
    s = str(value).strip()
    if s.endswith('.0'):
        s = s[:-2]
    if not s or not s.isdigit():
        return None
    return s.zfill(8)


def chunks(items, size=35):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def arcgis_query(layer, where, fields='*'):
    """Fetch all records for a SQL filter, respecting the service record limit."""
    result = []
    offset = 0
    limit = 1000
    while True:
        params = {
            'f': 'json',
            'where': where,
            'outFields': fields,
            'returnGeometry': 'false',
            'resultOffset': offset,
            'resultRecordCount': limit,
            'orderByFields': 'objectid ASC',
        }
        for attempt in range(5):
            try:
                r = session.get(f'{BASE}/{layer}/query', params=params, timeout=90)
                r.raise_for_status()
                payload = r.json()
                if 'error' in payload:
                    raise RuntimeError(f'ArcGIS API error: {payload["error"]}')
                features = payload['features']
                break
            except (requests.RequestException, ValueError, KeyError) as exc:
                if attempt == 4:
                    raise RuntimeError(f'Query failed: layer={layer}, where={where}') from exc
                time.sleep(2 ** attempt)
        records = [f['attributes'] for f in features]
        result.extend(records)
        if len(records) < limit and not payload.get('exceededTransferLimit', False):
            break
        if not records:
            raise RuntimeError(f'Pagination stalled on layer {layer}, where={where}')
        offset += len(records)
    return result


def download_by_values(layer, field, values, text_values=False):
    records = []
    groups = list(chunks(values))
    for i, group in enumerate(groups, 1):
        if text_values:
            choices = ','.join("'" + str(v).replace("'", "''") + "'" for v in group)
        else:
            choices = ','.join(str(int(v)) for v in group)
        where = f'{field} IN ({choices})'
        records.extend(arcgis_query(layer, where))
        print(f'Layer {layer}: {i}/{len(groups)} groups; {len(records)} records')
        time.sleep(0.15)
    return pd.DataFrame.from_records(records)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    lakes = pd.read_parquet(LAKES_PATH)
    if not {'unique_guid', 'dowlknum'}.issubset(lakes.columns):
        raise ValueError('Expected unique_guid and dowlknum in bwca_lakes.parquet')
    lakes = lakes[['unique_guid', 'dowlknum']].copy()
    lakes['dowlknum'] = lakes['dowlknum'].map(normalized_dow)
    dow_ids = sorted(lakes['dowlknum'].dropna().unique().tolist())
    print(f'{len(lakes)} BWCA polygons; {len(dow_ids)} distinct valid DOW lake IDs')

    # Layer 0 supplies the crosswalk between the LakeFinder/DOW ID and the
    # ArcGIS fw_id, avoiding reliance on the incomplete fw_id in our lake master.
    surveyed = download_by_values(0, 'dowlknum', dow_ids, text_values=True)
    if surveyed.empty:
        raise RuntimeError('Layer 0 returned no surveyed BWCA lakes. Check service schema.')
    surveyed['dowlknum'] = surveyed['dowlknum'].map(normalized_dow)
    surveyed.to_parquet(OUTPUT / 'dnr_arcgis_surveyed_lakes.parquet', index=False)

    fw_ids = sorted({int(v) for v in surveyed['fw_id'].dropna()})
    surveys = download_by_values(1, 'fw_id', fw_ids)
    if not surveys.empty:
        surveys = surveys.drop_duplicates(subset=['objectid'])
    surveys.to_parquet(OUTPUT / 'dnr_arcgis_all_surveys.parquet', index=False)

    # Crosswalk may be one-to-many (DOW number or fw_id shared across rows).
    # Retain all matches rather than silently deciding two lakes are identical.
    links = surveyed[['dowlknum', 'fw_id']].drop_duplicates()
    survey_counts = (surveys.groupby('fw_id').size().rename('arcgis_survey_count')
                     if not surveys.empty else pd.Series(dtype=int, name='arcgis_survey_count'))
    links = links.join(survey_counts, on='fw_id')
    links['arcgis_survey_count'] = links['arcgis_survey_count'].fillna(0).astype(int)
    coverage = lakes.merge(links, on='dowlknum', how='left')
    coverage['in_arcgis_surveyed_lakes'] = coverage['fw_id'].notna()
    coverage.to_parquet(OUTPUT / 'dnr_arcgis_bwca_coverage.parquet', index=False)

    print('\nSaved:')
    print(' ', OUTPUT / 'dnr_arcgis_surveyed_lakes.parquet', len(surveyed))
    print(' ', OUTPUT / 'dnr_arcgis_all_surveys.parquet', len(surveys))
    print(' ', OUTPUT / 'dnr_arcgis_bwca_coverage.parquet', len(coverage))

    no_data_path = OUTPUT / 'dnr_no_data.parquet'
    if no_data_path.exists():
        no_data = pd.read_parquet(no_data_path)
        if 'dowlknum' in no_data.columns:
            no_data_ids = {v for v in no_data['dowlknum'].map(normalized_dow) if v}
            found = coverage.loc[
                coverage['dowlknum'].isin(no_data_ids)
                & (coverage['arcgis_survey_count'].fillna(0) > 0),
                ['unique_guid', 'dowlknum', 'fw_id', 'arcgis_survey_count']
            ].drop_duplicates()
            found.to_parquet(OUTPUT / 'dnr_no_data_with_arcgis_surveys.parquet', index=False)
            print(f'\nPreviously no-data lake features with ArcGIS surveys: {len(found)}')
            print(' ', OUTPUT / 'dnr_no_data_with_arcgis_surveys.parquet')
        else:
            print('\nSkipping no-data comparison: no dowlknum column found.')


if __name__ == '__main__':
    main()
