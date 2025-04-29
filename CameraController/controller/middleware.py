import json
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
import logging

logger = logging.getLogger(__name__)

class JsonErrorMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        logger.exception("Unhandled server error")
        return JsonResponse(
            {'error': 'Internal Server Error', 'exception': str(exception)},
            status=500
        )

    def process_response(self, request, response):
        if response.status_code == 404 and not isinstance(response, JsonResponse):
            return JsonResponse({'error': 'Not Found'}, status=404)
        if response.status_code == 405 and not isinstance(response, JsonResponse):
            return JsonResponse({'error': 'Method Not Allowed'}, status=405)
        return response
