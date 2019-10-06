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

logger = logging.getLogger("django")


def redirect_url(payment):
    return "https://pec.shaparak.ir/NewIPG/?token={}".format(payment.token)


def redirect_data(request: HttpRequest, payment):
    # s = str(request.build_absolute_uri(reverse('pardakht:callback_url',
    #                                            args=[payment.slug, name]))).replace('http://', 'https://')

    return {}


def send_request(method, data):
    ws_method = getattr(client.service, method)
    result = ws_method(data)
    return result


def get_token(request: HttpRequest, payment):
    merchant_id = getattr(settings, str(name+'_merchant_id').upper(), 'none')
    callback_url = str(request.build_absolute_uri(reverse('pardakht:callback_url',
                                                          args=[payment.slug, name]))).replace('http://', 'https://')
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
        return result.Token

    else:
        logger.error("Couldn't get payment token from parsian")
        return None


def verify(request, payment):
    logger.debug(request.POST.get('status'))
    logger.debug(request.POST.get('RRN'))
    if request.POST.get('status') != ['0']:
        payment.state = payment.STATE_FAILURE
        payment.payment_result = str(request.POST.get('status'))
        payment.save()
        return

    merchant_id = getattr(settings, str(name + '_merchant_id').upper(), 'none')
    if merchant_id == 'none':
        logger.error('Merchant ID not in settings.\nDefine your merchant id in settings.py as ' + str(
            name + '_merchant_id').upper())
        return None
    order_id =  request.POST.get('OrderId')[0]
    if payment.trace_number != int(order_id):
        logger.warning('Manipulation')
        return
    ref_number = int(order_id)
    if Payment.objects.filter(ref_number=ref_number).exists():
        payment.state = payment.STATE_FAILURE
        payment.payment_result = 'MANIPULATION'
        payment.save()
        return
    else:
        payment.ref_number = ref_number
        payment.save()

    if int(request.POST.get('RRN')[0]) > 0:
        verification_data = {
                            'LoginAccount': merchant_id,
                            'Token': int(request.POST.get('Token')[0])
                            }
        verify_url = "https://pec.shaparak.ir/NewIPGServices/Confirm/ConfirmService.asmx?wsdl"
        verify_client = Client(verify_url)
        verify_method = getattr(verify_client.service, 'ConfirmPayment')
        verify_result = verify_method(verification_data)
        logger.debug(verification_result)

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
