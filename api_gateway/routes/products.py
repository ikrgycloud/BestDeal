from fastapi import APIRouter
from pydantic import BaseModel
import uuid
from rabbitmq.publisher import publish_event
import json
import os
from routes.database import MongoDatabase

router = APIRouter()
mongo_db = MongoDatabase()

class SearchRequest(BaseModel):
    keyword: str

class BestDealsRequest(BaseModel):
    keyword: str

@router.post("/search")
def search_product(payload: SearchRequest):
    request_id = str(uuid.uuid4())

    publish_event(
        event_type="SEARCH_PRODUCT",
        data={
            "requestId": request_id,
            "keyword": payload.keyword
        }
    )

    return {
        "requestId": request_id,
        "status": "PROCESSING"
    }

@router.post("/best-deals")
def get_best_deals(payload: BestDealsRequest):
    request_id = str(uuid.uuid4())

    publish_event(
        event_type="GET_BEST_DEALS",
        data={
            "requestId": request_id,
            "keyword": payload.keyword
        }
    )

    return {
        "requestId": request_id,
        "status": "PROCESSING"
    }

@router.get("/results/{request_id}")
def get_results(request_id: str, page: int = 1, limit: int = 10):
    # Fetch results from MongoDB
    all_data = mongo_db.get_search_results(request_id)

    if all_data:
        
        if page < 1:
            page = 1

        start_index = (page - 1) * limit
        end_index = start_index + limit
        paginated_data = all_data[start_index:end_index]
        total_pages = (len(all_data) + limit - 1) // limit

        # Debug print to verify pagination logic in terminal
        print(f" [API] Serving Request: {request_id} | Page: {page}/{total_pages} | Results: {len(paginated_data)}")

        return {
            "status": "COMPLETED",
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "page_numbers": list(range(1, total_pages + 1)),
            "has_next": page < total_pages,
            "has_previous": page > 1,
            "next_page": page + 1 if page < total_pages else None,
            "prev_page": page - 1 if page > 1 else None,
            "total_results": len(all_data),
            "data": paginated_data
        }

    return {"status": "PROCESSING"}
