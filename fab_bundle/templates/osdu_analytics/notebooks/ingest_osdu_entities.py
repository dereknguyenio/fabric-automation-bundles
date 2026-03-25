# Fabric Notebook: Ingest OSDU Entities from ADME
# Pulls well, wellbore, and survey entities via OSDU Search API
# and lands them as raw JSON in the bronze lakehouse.

import json
import requests
from datetime import datetime
from azure.identity import DefaultAzureCredential
from pyspark.sql import functions as F

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------

ADME_ENDPOINT = spark.conf.get("spark.fabric.bundle.adme_endpoint", "https://myorg.energy.azure.com")
DATA_PARTITION = "opendes"
OSDU_API_VERSION = "v3"

ENTITY_KINDS = [
    "osdu:wks:master-data--Well:1.0.0",
    "osdu:wks:master-data--Wellbore:1.0.0",
    "osdu:wks:work-product-component--WellboreTrajectory:1.0.0",
]

RAW_TABLE = "osdu_raw_entities"

# -----------------------------------------------------------------------
# Authentication
# -----------------------------------------------------------------------

credential = DefaultAzureCredential()
token = credential.get_token(f"{ADME_ENDPOINT}/.default").token

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "data-partition-id": DATA_PARTITION,
}

# -----------------------------------------------------------------------
# Fetch entities via OSDU Search API
# -----------------------------------------------------------------------

def search_osdu_entities(kind: str, limit: int = 1000) -> list[dict]:
    """Search OSDU for entities of a given kind."""
    url = f"{ADME_ENDPOINT}/api/search/{OSDU_API_VERSION}/query"
    
    all_results = []
    offset = 0
    
    while True:
        body = {
            "kind": kind,
            "limit": limit,
            "offset": offset,
            "returnedFields": ["*"],
        }
        
        response = requests.post(url, headers=headers, json=body, timeout=120)
        response.raise_for_status()
        
        data = response.json()
        results = data.get("results", [])
        all_results.extend(results)
        
        total = data.get("totalCount", 0)
        offset += len(results)
        
        if offset >= total or not results:
            break
    
    return all_results

# -----------------------------------------------------------------------
# Ingest each entity kind
# -----------------------------------------------------------------------

ingestion_time = datetime.utcnow().isoformat()
all_entities = []

for kind in ENTITY_KINDS:
    kind_short = kind.split("--")[-1].split(":")[0]
    print(f"Fetching {kind_short}...")
    
    try:
        entities = search_osdu_entities(kind)
        print(f"  Retrieved {len(entities)} {kind_short} entities")
        
        for entity in entities:
            all_entities.append({
                "entity_kind": kind,
                "entity_kind_short": kind_short,
                "entity_id": entity.get("id", ""),
                "entity_json": json.dumps(entity),
                "ingestion_timestamp": ingestion_time,
            })
    except Exception as e:
        print(f"  ERROR fetching {kind_short}: {e}")

# -----------------------------------------------------------------------
# Write to Bronze Lakehouse
# -----------------------------------------------------------------------

if all_entities:
    df = spark.createDataFrame(all_entities)
    
    df.write \
        .format("delta") \
        .mode("append") \
        .partitionBy("entity_kind_short") \
        .saveAsTable(RAW_TABLE)
    
    print(f"\nIngested {len(all_entities)} total entities to {RAW_TABLE}")
else:
    print("No entities retrieved — check ADME connectivity and permissions")
