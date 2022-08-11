function motionjpeg(id) {
    var image = $(id), src;

    if (!image.length) return;

    src = image.attr("src");
    if (src.indexOf("?") < 0) {
        image.attr("src", src + "?"); // must have querystring
    }

    image.on("load", function() {
        // this cause the load event to be called "recursively"
        this.src = this.src.replace(/\?[^\n]*$/, "?") +
            (new Date()).getTime(); // 'this' refers to the image
    });
}