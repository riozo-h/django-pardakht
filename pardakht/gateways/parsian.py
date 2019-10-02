from django.http import HttpRequest
from zeep import Client
from django.conf import settings
from django.urls import reverse
import logging
# from ..models import Payment

name = 'parsian'
display_name = 'پارسیان'
webservice_url = "https://pec.shaparak.ir/NewIPGServices/Sale/SaleService.asmx?wsdl"

client = Client(webservice_url)

logger = logging.getLogger(__name__)


def redirect_url(payment):
    return "https://pec.shaparak.ir/NewIPG/?token="


def redirect_data(request: HttpRequest, payment):
    s = str(request.build_absolute_uri(reverse('pardakht:callback_url',
                                               args=[payment.slug, name]))).replace('http://', 'https://')
    return {
        'Token': payment.token,
        'RedirectURL': s
    }


def send_request(method, data):
    ws_method = getattr(client.service, method)
    result = ws_method(data)
    return result


def get_token(request: HttpRequest, payment):
    merchant_id = getattr(settings, str(name+'_merchant_id').upper(), 'none')
    callback_url = getattr(settings, str(name+'_callback_url').upper(), 'none')
    if merchant_id == 'none':
        logger.error('Merchant ID not in settings.\nDefine your merchant id in settings.py as '
                     + str(name+'_merchant_id').upper())
        return None
    request_data = {
        'LoginAccount': merchant_id,
        'OrderId': payment.trace_number,
        'Amount': payment.price * 10,
        'CallBackUrl': callback_url
    }
    result = send_request('SalePaymentRequest', request_data)
    if result.Status == 0:
        payment.gateway = name
        payment.save()
        return result

    else:
        logger.error("Couldn't get payment token from parsian")
        logger.error(print(result))

        return None

def verify(request, payment):
    if request.POST.get('Status') != 0:
        payment.state = payment.STATE_FAILURE
        payment.payment_result = str(request.POST.get('Status'))
        payment.save()
        return

    merchant_id = getattr(settings, str(name + '_merchant_id').upper(), 'none')
    if merchant_id == 'none':
        logger.error('Merchant ID not in settings.\nDefine your merchant id in settings.py as ' + str(
            name + '_merchant_id').upper())
        return None

    if payment.trace_number != request.POST.get('OrderId'):
        logger.warning('Manipulation')
        return

    ref_number = request.POST.get('OrderId')
    if Payment.objects.filter(ref_number=ref_number).exists():
        payment.state = payment.STATE_FAILURE
        payment.payment_result = 'MANIPULATION'
        payment.save()
        return
    else:
        payment.ref_number = ref_number
        payment.save()

    if int(request.POST.get('RRN')) > 0:
        verification_data = {
                            'LoginAccount': merchant_id,
                            'Token': request.POST.get('Token')
                            }
        verify_url = "https://pec.shaparak.ir/NewIPGServices/Confirm/ConfirmService.asmx?wsdl"
        verify_client = Client(verify_url)
        verify_method = getattr(verify_client.service, 'ConfirmPayment')
        verify_result = verify_method(verification_data)

        if verify_result.Status == 0:
            payment.state = payment.STATE_SUCCESS
            result = "Successful Verified"
        else:
            payment.state = payment.STATE_FAILURE
            result = "Payment Failure"

        payment.verification_result = str(result)
        payment.save()
    else:
        return
