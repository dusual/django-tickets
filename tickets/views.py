from django.conf import settings
from django.shortcuts import render_to_response, redirect, get_object_or_404
from django.http import HttpResponseBadRequest, HttpResponse, HttpResponseForbidden
from django.views.generic.simple import direct_to_template
from django import forms
from django.template import RequestContext
from django.forms.util import ErrorList
from django.contrib.auth.decorators import login_required

from paypal.standard.forms import PayPalPaymentsForm
from tickets.models import *
from tickets.forms import *

import csv

@login_required
def purchase_data_csv (request):
    if not request.user.is_staff:
        return HttpResponseForbidden("you must have admin access")
    response = HttpResponse(mimetype='text/csv')
    response['Content-Disposition'] = 'attachment; filename=ticketpurchases.csv'
    purchases = TicketPurchase.objects.all()
    writer = csv.writer(response)
    writer.writerow(['date', 'amount', 'name', 'status'])
    for p in purchases:
        writer.writerow([p.date, p.amount,p.name, p.status])
    return response

@login_required
def ticket_data_csv (request):
    if not request.user.is_staff:
        return HttpResponseForbidden("you must have admin access")
    response = HttpResponse(mimetype='text/csv')
    response['Content-Disposition'] = 'attachment; filename=ticketdata.csv'
    tickets = Ticket.objects.filter(purchase__status__icontains="completed").order_by('event')
    writer = csv.writer(response)
    writer.writerow(['attendee', 'ticket_type', 'event'])
    for t in tickets:
        writer.writerow([t, t.ticket_type ,t.event])
    return response

def initiated(request):
    pass
    
def purchase(request,event_slug=None):
    event = get_object_or_404(TicketedEvent,slug=event_slug)
    TicketFormSet = forms.formsets.formset_factory(TicketForm,max_num=event.purchase_limit,extra=event.purchase_limit)
    type_qs = event.ticket_types.get_query_set()
    
    if not event.tickets_available():
        return redirect('sold_out')
    def patch_formset(formset,event):
        for form in formset.forms:
            form.fields['ticket_type'].queryset = type_qs
            if event.attendee_required:
                del (form.fields['qty'])
            else:
                del (form.fields['name'])
        
    if request.method == 'POST':
        formset = TicketFormSet(request.POST)
        patch_formset(formset,event)
        purchaseform = TicketPurchaseForm(request.POST,prefix='purchase')
        if formset.is_valid() and purchaseform.is_valid():
            total = 0
            for form in formset.forms:
                cd = form.cleaned_data
                if form.cleaned_data['ticket_type']:
                    total += form.cleaned_data['ticket_type'].price
            if total:
                purchase = TicketPurchase(amount=total,**purchaseform.cleaned_data)
                purchase.save()
                # @@ need a code branch here to handle anon qty based purchase
                tickets = []
                for form in formset.forms:
                    if event.attendee_required and form.cleaned_data['attendee']:
                        ticket = Ticket(purchase=purchase,event=event,**form.cleaned_data)
                        ticket.save()
                        tickets.append(ticket)
            
                if request.user.is_authenticated() and 'cash' in request.POST:
                    purchase.status = "completed cash"
                    purchase.save()
                    return HttpResponse ("Cash Payment Recorded")

                
                paypal_dict = {
                    "business": settings.PAYPAL_RECEIVER_EMAIL,
                    "amount": total,
                    "item_name": "tickets for: %s (%s)" % (event.name,len(tickets)),
                    "invoice": purchase.invoice,
                    "notify_url": settings.PAYPAL_NOTIFY_URL,
                    "return_url": settings.PAYPAL_RETURN_URL,
                    "cancel_return": settings.PAYPAL_CANCEL_URL,

                }
            
                paypal_form = PayPalPaymentsForm(initial=paypal_dict)

                context = {'form': paypal_form,'purchase':purchase,'event':event,'tickets':tickets}
            

                return render_to_response("tickets/payment.html", context,context_instance=RequestContext(request))
            else: # no total
                # @@ not sure why this error appears in the middle of the formset...
                form._errors['__all__']  = ErrorList(["You have to buy at least one ticket to continue"])
    else:
        purchaseform = TicketPurchaseForm(prefix='purchase')
        data = {}
        if event.default_ticket_type:
            # set first ticket to default type
            data = [{} for i in range(event.purchase_limit)]
            data[0] = {'ticket_type':event.default_ticket_type.id}
        formset = TicketFormSet(initial=data)
        patch_formset(formset,event)
    context = {
            "purchaseform":purchaseform,
            'ticketformset':formset,
            "event":event,
            }
    if request.user.is_authenticated():
        context['cash_ok']=True
        print "cash ok"
    
    return render_to_response("tickets/ticketpurchase_form.html",context,context_instance=RequestContext(request))
    return HttpResponse(event.name)