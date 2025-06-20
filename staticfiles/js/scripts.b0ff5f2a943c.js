/*!
* Start Bootstrap - Freelancer v7.0.7 (https://startbootstrap.com/theme/freelancer)
* Copyright 2013-2023 Start Bootstrap
* Licensed under MIT (https://github.com/StartBootstrap/startbootstrap-freelancer/blob/master/LICENSE)
*/
//
// Scripts
// 

function showErrorMessage(element, message) {
    const errorElement = element.parentElement.querySelector('.invalid-feedback');
    errorElement.textContent = message;
    element.classList.toggle('is-invalid', message !== '');
}

function validateEmail(email) {
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailPattern.test(email);
}

function validatePhoneNumber(phoneNumber) {
    return /^\d+$/.test(phoneNumber);
}

window.addEventListener('DOMContentLoaded', event => {

    // Navbar shrink function
    var navbarShrink = function () {
        const navbarCollapsible = document.body.querySelector('#mainNav');
        if (!navbarCollapsible) {
            return;
        }
        if (window.scrollY === 0) {
            navbarCollapsible.classList.remove('navbar-shrink')
        } else {
            navbarCollapsible.classList.add('navbar-shrink')
        }

    };

    // Shrink the navbar 
    navbarShrink();

    // Shrink the navbar when page is scrolled
    document.addEventListener('scroll', navbarShrink);

    // Activate Bootstrap scrollspy on the main nav element
    const mainNav = document.body.querySelector('#mainNav');
    if (mainNav) {
        new bootstrap.ScrollSpy(document.body, {
            target: '#mainNav',
            rootMargin: '0px 0px -40%',
        });
    };

    // Collapse responsive navbar when toggler is visible
    const navbarToggler = document.body.querySelector('.navbar-toggler');
    const responsiveNavItems = [].slice.call(
        document.querySelectorAll('#navbarResponsive .nav-link')
    );
    responsiveNavItems.map(function (responsiveNavItem) {
        responsiveNavItem.addEventListener('click', () => {
            if (window.getComputedStyle(navbarToggler).display !== 'none') {
                navbarToggler.click();
            }
        });
    });

    const emailField = document.querySelector('[name="email"]');
    const phoneNumberField = document.querySelector('[name="phone_number"]');

    emailField.addEventListener('input', () => {
        if (!validateEmail(emailField.value)) {
            showErrorMessage(emailField, 'Invalid email format');
        } else {
            showErrorMessage(emailField, '');
        }
    });

    phoneNumberField.addEventListener('input', () => {
        if (!validatePhoneNumber(phoneNumberField.value)) {
            showErrorMessage(phoneNumberField, 'Phone number should only contain digits');
        } else {
            showErrorMessage(phoneNumberField, '');
        }
    });

    const contactForm = document.getElementById('contactForm');
    const successMessage = document.getElementById('successMessage');
    const errorMessage = document.getElementById('errorMessage');

    contactForm.addEventListener('submit', async (event) => {
        event.preventDefault();

        const formData = new FormData(contactForm);
        const response = await fetch(contactForm.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',  // DjangoがAjaxリクエストとして認識するために必要です。
                'X-CSRFToken': contactForm.querySelector('[name="csrfmiddlewaretoken"]').value,
            },
        });

        if (response.ok) {
            contactForm.reset();
            successMessage.style.display = 'block';
            errorMessage.style.display = 'none';
        } else {
            // エラーハンドリング
            successMessage.style.display = 'none';
            errorMessage.style.display = 'block';
        }
    });
    
    const successCloseButton = document.querySelector('#successMessage .btn-close');
    const errorCloseButton = document.querySelector('#errorMessage .btn-close');

    successCloseButton.addEventListener('click', () => {
        successMessage.style.display = 'none';
    });

    errorCloseButton.addEventListener('click', () => {
        errorMessage.style.display = 'none';
    });
});
