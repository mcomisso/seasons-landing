(() => {
    "use strict";

    const contentByPath = {
        "verify-contact-email": {
            title: "Opening Seasons",
            message: "Continue in Seasons to verify your Contact Email."
        },
        "replace-contact-email": {
            title: "Opening Seasons",
            message: "Continue in Seasons to verify your new Contact Email."
        },
        "recover-account": {
            title: "Opening Seasons",
            message: "Continue in Seasons to recover your account."
        }
    };

    const path = window.location.pathname.split("/").filter(Boolean).pop();
    const content = contentByPath[path];
    const title = document.querySelector("h1");
    const message = document.querySelector("[data-message]");
    const openButton = document.querySelector("[data-open-seasons]");

    if (!content || !window.location.hash) {
        title.textContent = "This link is incomplete";
        message.textContent = "Return to the Seasons app and request a new email link.";
        openButton.setAttribute("aria-disabled", "true");
        return;
    }

    title.textContent = content.title;
    message.textContent = content.message;

    // The bearer proof stays in the fragment. It is never sent to this website.
    const deepLink = `seasons://${path}${window.location.hash}`;
    openButton.href = deepLink;

    window.location.href = deepLink;
})();
