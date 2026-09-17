const vscode = require('vscode');

const DEVICE_SCOPES = ['repo', 'user:email'];

async function activate(context) {
  context.subscriptions.push(vscode.commands.registerCommand(
    'github-authentication.device-code-flow.authentication',
    async () => vscode.authentication.getSession('github', DEVICE_SCOPES, { createIfNone: true }),
  ));
  context.subscriptions.push(vscode.commands.registerCommand(
    'github-authentication.device-code-flow.remove-token',
    () => vscode.commands.executeCommand('workbench.action.accounts.manage'),
  ));
}

module.exports = { activate };
