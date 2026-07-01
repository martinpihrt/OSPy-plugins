(function () {
    let frames = [];
    let frameIndex = 0;
    let frameTimer = null;

    function isHomePage() {
        return window.location.pathname === "/" && jQuery("#options").length > 0;
    }

    function ensureWidget() {
        if (jQuery("#chmiHomeWidget").length) {
            return;
        }

        let style = document.createElement("style");
        style.innerHTML = `
            .chmiHomeWidgetHost {
                position: relative;
                box-sizing: border-box;
                min-height: 246px;
                padding-right: 350px;
                z-index: 0;
            }

            #chmiHomeWidget {
                position: absolute;
                top: 8px;
                right: 8px;
                bottom: 8px;
                width: 318px;
                max-width: calc(100% - 16px);
                margin: 0;
                border: 2px solid #2E3959;
                border-radius: 4px;
                background: #ffffff;
                overflow: hidden;
                cursor: pointer;
                z-index: 0;
                display: flex;
                flex-direction: column;
                box-sizing: border-box;
            }

            #chmiHomeWidget img {
                display: block;
                width: 100%;
                min-height: 0;
                flex: 1 1 auto;
                object-fit: contain;
                background: #ffffff;
            }

            #chmiHomeWidgetLabel {
                padding: 2px 6px;
                background: #2E3959;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                line-height: 16px;
                text-align: left;
            }

            #chmiHomeWidgetTimeline {
                display: flex;
                flex: 0 0 auto;
                gap: 2px;
                padding: 3px;
                background: #f1f1f1;
            }

            #chmiHomeWidgetTimeline span {
                flex: 1;
                height: 4px;
                border-radius: 2px;
                background: #2b7f2b;
            }

            #chmiHomeWidgetTimeline span.forecast {
                background: #d69b00;
            }

            #chmiHomeWidgetTimeline span.active {
                background: #2E3959;
            }

            @media (max-width: 900px) {
                .chmiHomeWidgetHost {
                    min-height: 0;
                    padding-right: 0;
                }

                #chmiHomeWidget {
                    position: relative;
                    top: auto;
                    right: auto;
                    bottom: auto;
                    width: calc(100% - 16px);
                    max-width: 318px;
                    height: 230px;
                    margin: 8px auto 0;
                }
            }
        `;
        document.head.appendChild(style);

        let widget = jQuery(`
            <div id="chmiHomeWidget" title="CHMI meteoradar">
                <div id="chmiHomeWidgetLabel">CHMI</div>
                <img id="chmiHomeWidgetImage" alt="CHMI radar">
                <div id="chmiHomeWidgetTimeline"></div>
            </div>
        `);
        widget.on("click", function () {
            window.location.href = "/plugins/chmi/settings";
        });

        let host = jQuery("#options").closest("#graph-container");
        host.addClass("chmiHomeWidgetHost");
        host.append(widget);
    }

    function updateTimeline() {
        let timeline = jQuery("#chmiHomeWidgetTimeline");
        timeline.empty();
        for (let i = 0; i < frames.length; i++) {
            let tick = jQuery("<span></span>");
            if (frames[i].type === "forecast") {
                tick.addClass("forecast");
            }
            if (i === frameIndex) {
                tick.addClass("active");
            }
            timeline.append(tick);
        }
    }

    function showFrame() {
        if (!frames.length) {
            return;
        }

        let frame = frames[frameIndex];
        jQuery("#chmiHomeWidgetImage").attr("src", frame.url + "&_=" + new Date().getTime());
        jQuery("#chmiHomeWidgetLabel").text(frame.label);
        updateTimeline();
        frameIndex = (frameIndex + 1) % frames.length;
    }

    function loadFrames() {
        if (!isHomePage()) {
            return;
        }

        jQuery.getJSON("/plugins/chmi/animation_json", function (data) {
            if (!data.enabled || !data.frames || !data.frames.length) {
                jQuery("#chmiHomeWidget").remove();
                jQuery(".chmiHomeWidgetHost").removeClass("chmiHomeWidgetHost");
                if (frameTimer) {
                    clearInterval(frameTimer);
                    frameTimer = null;
                }
                return;
            }

            frames = data.frames;
            if (frameIndex >= frames.length) {
                frameIndex = 0;
            }
            ensureWidget();
            if (!frameTimer) {
                showFrame();
                frameTimer = setInterval(showFrame, 1000);
            }
        });

        setTimeout(loadFrames, 30000);
    }

    jQuery(document).ready(loadFrames);
})();
