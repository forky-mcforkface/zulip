import type {ElementHandle, Page} from "puppeteer";

import common from "../puppeteer_lib/common";

async function test_subscription_button(page: Page): Promise<void> {
    const stream_selector = "[data-stream-name='Venice']";
    const button_selector = `${stream_selector} .sub_unsub_button`;
    const subscribed_selector = `${button_selector}.checked`;
    const unsubscribed_selector = `${button_selector}:not(.checked)`;

    async function subscribed(): Promise<ElementHandle | null> {
        await page.waitForFunction(
            () => $(".stream_settings_header .sub_unsub_button").text().trim() === "Unsubscribe",
        );
        return await page.waitForSelector(subscribed_selector, {visible: true});
    }

    async function unsubscribed(): Promise<ElementHandle | null> {
        await page.waitForFunction(
            () => $(".stream_settings_header .sub_unsub_button").text().trim() === "Subscribe",
        );
        return await page.waitForSelector(unsubscribed_selector, {visible: true});
    }

    // Make sure that Venice is even in our list of streams.
    await page.waitForSelector(stream_selector, {visible: true});
    await page.waitForSelector(button_selector, {visible: true});

    await page.click(stream_selector);

    // Note that we intentionally re-find the button after each click, since
    // the live-update code may replace the whole row.
    let button;

    // We assume Venice is already subscribed, so the first line here
    // should happen immediately.
    button = await subscribed();

    // Toggle subscriptions several times.
    for (let i = 0; i < 10; i += 1) {
        await button!.click();
        button = await unsubscribed();
        await button!.click();
        button = await subscribed();
    }
}

async function subscriptions_tests(page: Page): Promise<void> {
    await common.log_in(page);
    await common.open_streams_modal(page);
    await test_subscription_button(page);
}

common.run_test(subscriptions_tests);
