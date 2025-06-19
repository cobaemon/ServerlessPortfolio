from django.views.generic import FormView
from django.http import HttpResponse
from .forms import ContactForm

class Top(FormView):
    template_name = 'index.html'
    form_class = ContactForm

    def form_valid(self, form):
        form.send_email()
        return HttpResponse("Form submission successful")
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form_class()
        return context
