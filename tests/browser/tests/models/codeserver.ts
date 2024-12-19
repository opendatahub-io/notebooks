// Copyright (c) 2019 Coder Technologies Inc.
// https://github.com/coder/code-server/blob/main/test/e2e/models/CodeServer.ts

import {Page} from "@playwright/test";
import * as path from "node:path";

/**
 * Class for managing code-server.
 */
export class CodeServer {
    private readonly logger = {
        debug: (x) => console.log(x),
        named: (name) => this.logger,
    }

    constructor(public readonly page: Page, public readonly url: string) {
    }

    /**
     * Checks if the editor is visible
     */
     async isEditorVisible(): Promise<boolean> {
        let editorSelector = "div.monaco-workbench"

        await this.page.waitForSelector(editorSelector, {timeout: 10000})  // this waits for initial load, let's wait longer
        const visible = await this.page.isVisible(editorSelector)

        this.logger.debug(`Editor is ${visible ? "not visible" : "visible"}!`)

        return visible
    }

    /**
     * Wait for a tab to open for the specified file.
     */
    async waitForTab(file: string): Promise<void> {
        await this.page.waitForSelector(`.tab :text("${path.basename(file)}")`)
    }

    /**
     * Focuses the integrated terminal by navigating through the command palette.
     *
     * This should focus the terminal no matter if it already has focus and/or is
     * or isn't visible already.  It will always create a new terminal to avoid
     * clobbering parallel tests.
     */
    async focusTerminal() {
        const doFocus = async (): Promise<boolean> => {
            await this.executeCommandViaMenus("Terminal: Create New Terminal")
            try {
                await this.page.waitForLoadState("load")
                await this.page.waitForSelector("textarea.xterm-helper-textarea:focus-within", { timeout: 5000 })
                return true
            } catch (error) {
                return false
            }
        }

        let attempts = 1
        while (!(await doFocus())) {
            ++attempts
            this.logger.debug(`no focused terminal textarea, retrying (${attempts}/∞)`)
        }

        this.logger.debug(`opening terminal took ${attempts} ${plural(attempts, "attempt")}`)
    }

    /**
     * Open a file by using menus.
     */
    async openFile(file: string) {
        await this.navigateMenus(["File", "Open File..."])
        await this.navigateQuickInput([path.basename(file)])
        await this.waitForTab(file)
    }

    /**
     * Navigate to the command palette via menus then execute a command by typing
     * it then clicking the match from the results.
     */
    async executeCommandViaMenus(command: string) {
        await this.navigateMenus(["View", "Command Palette..."])

        await this.page.keyboard.type(command)

        await this.page.hover(`text=${command}`)
        await this.page.click(`text=${command}`)
    }

    /**
     * Navigate through the menu, retrying on failure.
     */
    async navigateMenus(menus: string[]): Promise<void> {
        await this.navigateItems(menus, '[aria-label="Application Menu"]', async (selector) => {
            await this.page.click(selector)
        })
    }

    /**
     * Navigate through a currently opened "quick input" widget, retrying on
     * failure.
     */
    async navigateQuickInput(items: string[]): Promise<void> {
        await this.navigateItems(items, ".quick-input-widget")
    }

    /**
     * Navigate through the items in the selector.  `open` is a function that will
     * open the menu/popup containing the items through which to navigation.
     */
    async navigateItems(items: string[], selector: string, open?: (selector: string) => void): Promise<void> {
        const logger = this.logger.named(selector)

        /**
         * If the selector loses focus or gets removed this will resolve with false,
         * signaling we need to try again.
         */
        const openThenWaitClose = async (ctx: Context) => {
            if (open) {
                await open(selector)
            }
            this.logger.debug(`watching ${selector}`)
            try {
                await this.page.waitForSelector(`${selector}:not(:focus-within)`)
            } catch (error) {
                if (!ctx.finished()) {
                    this.logger.debug(`${selector} navigation: ${(error as any).message || error}`)
                }
            }
            return false
        }

        /**
         * This will step through each item, aborting and returning false if
         * canceled or if any navigation step has an error which signals we need to
         * try again.
         */
        const navigate = async (ctx: Context) => {
            const steps: Array<{ fn: () => Promise<unknown>; name: string }> = [
                {
                    fn: () => this.page.waitForSelector(`${selector}:focus-within`),
                    name: "focus",
                },
            ]

            for (const item of items) {
                // Normally these will wait for the item to be visible and then execute
                // the action. The problem is that if the menu closes these will still
                // be waiting and continue to execute once the menu is visible again,
                // potentially conflicting with the new set of navigations (for example
                // if the old promise clicks logout before the new one can). By
                // splitting them into two steps each we can cancel before running the
                // action.
                steps.push({
                    fn: () => this.page.hover(`${selector} :text-is("${item}")`, { trial: true }),
                    name: `${item}:hover:trial`,
                })
                steps.push({
                    fn: () => this.page.hover(`${selector} :text-is("${item}")`, { force: true }),
                    name: `${item}:hover:force`,
                })
                steps.push({
                    fn: () => this.page.click(`${selector} :text-is("${item}")`, { trial: true }),
                    name: `${item}:click:trial`,
                })
                steps.push({
                    fn: () => this.page.click(`${selector} :text-is("${item}")`, { force: true }),
                    name: `${item}:click:force`,
                })
            }

            for (const step of steps) {
                try {
                    logger.debug(`navigation step: ${step.name}`)
                    await step.fn()
                    if (ctx.canceled()) {
                        logger.debug("navigation canceled")
                        return false
                    }
                } catch (error) {
                    logger.debug(`navigation: ${(error as any).message || error}`)
                    return false
                }
            }
            return true
        }

        // We are seeing the menu closing after opening if we open it too soon and
        // the picker getting recreated in the middle of trying to select an item.
        // To counter this we will keep trying to navigate through the items every
        // time we lose focus or there is an error.
        let attempts = 1
        let context = new Context()
        while (!(await Promise.race([openThenWaitClose(context), navigate(context)]))) {
            ++attempts
            logger.debug(`closed, retrying (${attempts}/∞)`)
            context.cancel()
            context = new Context()
        }

        context.finish()
        logger.debug(`navigation took ${attempts} ${plural(attempts, "attempt")}`)
    }
}

function plural(count: number, singular: string) {
    return `${count} ${singular}s`
}

class Context {
    private _canceled = false
    private _done = false
    public canceled(): boolean {
        return this._canceled
    }
    public finished(): boolean {
        return this._done
    }
    public cancel(): void {
        this._canceled = true
    }
    public finish(): void {
        this._done = true
    }
}
