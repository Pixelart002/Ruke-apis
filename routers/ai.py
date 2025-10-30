# routes/ai_route.py

import httpx
from fastapi import APIRouter, HTTPException, Query

# Create a new router instance. This will be included by main.py
router = APIRouter()

# Define the external API endpoint
MISTRAL_API_URL = "https://mistral-ai-three.vercel.app/"


@router.get("/ai")
async def get_ai_response(
    # Use Query() to define the query parameters for your /ai endpoint
    # We rename 'question' to 'question_param' when sending to the external API
    user_id: str = Query(..., description="The ID of the user"),
    question: str = Query(..., description="The question to ask the AI")
):
    """
    This endpoint takes a user_id and a question, forwards them to the
    Mistral AI API, and returns the response.
    """
    
    # Prepare the parameters for the external API call
    # Note: We map our 'question' variable to the 'question_param' key
    #       as required by the external service.
    external_params = {
        "id": user_id,
        "question_param": question
    }

    # Use httpx.AsyncClient for asynchronous requests
    try:
        async with httpx.AsyncClient() as client:
            # Make the GET request to the external API
            print(f"Forwarding request to: {MISTRAL_API_URL} with params: {external_params}")
            
            res = await client.get(MISTRAL_API_URL, params=external_params)

            # Raise an exception if the API returns an error (4xx or 5xx)
            res.raise_for_status()

            # Return the JSON response from the external API directly
            return res.json()

    except httpx.HTTPStatusError as exc:
        # Handle errors from the external API (e.g., 404, 500)
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Error from external AI API: {exc.response.text}"
        )
    except Exception as e:
        # Handle other unexpected errors (e.g., network issues)
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred: {str(e)}"
        )