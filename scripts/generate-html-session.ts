/**
 * @license
 * Copyright 2025 Google LLC
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { render } from 'ink';
import fs from 'node:fs';
import path from 'node:path';
import AnsiToHtml from 'ansi-to-html';
import { HistoryItemDisplay } from '../packages/cli/src/ui/components/HistoryItemDisplay.js';
import { SettingsContext } from '../packages/cli/src/ui/contexts/SettingsContext.js';
import { loadSettings } from '../packages/cli/src/config/settings.js';
import { TerminalProvider } from '../packages/cli/src/ui/contexts/TerminalContext.js';
import { UIStateContext } from '../packages/cli/src/ui/contexts/UIStateContext.js';
import { ConfigContext } from '../packages/cli/src/ui/contexts/ConfigContext.js';
import { StreamingContext } from '../packages/cli/src/ui/contexts/StreamingContext.js';
import { Box } from 'ink';

interface ConversationRecord {
  messages: any[];
}

function generateHistoryItemsFromMessages(messages: any[]): any[] {
  const items: any[] = [];

  for (const message of messages) {
    if (message.type === 'user') {
      const text = message.content?.map((p: any) => p.text).join('') || '';
      items.push({
        id: message.id,
        type: 'user',
        text,
      });
    } else if (message.type === 'gemini') {
      const text = message.content?.map((p: any) => p.text).join('') || '';

      if (message.thoughts && message.thoughts.length > 0) {
        items.push({
          id: `${message.id}-thinking`,
          type: 'thinking',
          thought: message.thoughts.map((t: any) => t.thought).join('\n'),
        });
      }

      if (message.toolCalls && message.toolCalls.length > 0) {
        items.push({
          id: `${message.id}-tools`,
          type: 'tool_group',
          tools: message.toolCalls.map((tc: any) => ({
            id: tc.id,
            toolName: tc.displayName || tc.name,
            args: tc.args,
            status: tc.status.toLowerCase() === 'success' ? 'success' : tc.status,
            resultDisplay: tc.resultDisplay,
            renderOutputAsMarkdown: tc.renderOutputAsMarkdown,
          })),
        });
      }

      if (text) {
        items.push({
          id: message.id,
          type: 'gemini',
          text,
        });
      }
    }
  }

  return items;
}

const App = ({ items, settings }: { items: any[]; settings: any }) => {
  return React.createElement(
    SettingsContext.Provider,
    { value: settings },
    React.createElement(
      TerminalProvider,
      null,
      React.createElement(
        ConfigContext.Provider,
        { value: {
            getScreenReader: () => false,
            getDebugMode: () => false,
            getUseBackgroundColor: () => false,
          } as any
        },
        React.createElement(
          UIStateContext.Provider,
          { value: { renderMarkdown: true, shellModeActive: false } as any },
          React.createElement(
            StreamingContext.Provider,
            { value: 'idle' as any },
            React.createElement(
              React.Fragment,
              null,
              React.createElement(
                Box,
                { flexDirection: 'column', paddingBottom: 1, paddingTop: 1 },
                items.map((item) =>
            React.createElement(
              Box,
              { key: item.id, marginBottom: 1 },
              React.createElement(HistoryItemDisplay, {
                item: item,
                terminalWidth: 120,
                isPending: false,
              })
            )
          )
        )
        )
      )
    )
    )
    )
  );
};

async function main() {
  const sessionFilePath = process.argv[2];

  if (!sessionFilePath) {
    console.error('Usage: npx tsx scripts/generate-html-session.ts <path-to-session.json>');
    process.exit(1);
  }

  const sessionData = fs.readFileSync(path.resolve(sessionFilePath), 'utf8');
  const session: ConversationRecord = JSON.parse(sessionData);

  const items = generateHistoryItemsFromMessages(session.messages);
  const settings = loadSettings();

  // Custom stdout to capture output
  let output = '';
  const customStdout = {
    write(str: string) {
      output += str;
    },
    columns: 120,
    rows: 80,
    on: () => {},
    off: () => {},
    emit: () => {},
    isTTY: true,
  } as any;

  const { unmount, clear } = render(
    React.createElement(App, { items, settings }),
    { stdout: customStdout, exitOnCtrlC: false, debug: true }
  );

  // Unmount immediately after rendering
  unmount();

  // Strip cursor show/hide escapes from the output
  output = output.replace(/\x1b\[\?25[lh]/g, '');

  // Ink sometimes writes multiple frames as state updates even if synchronous.
  // It uses various clear sequences. We'll find the last `\x1b[0G` which resets cursor
  // and splits frames. Or we can just use the last frame rendered by splitting on ANSI clear lines.
  // Actually, we can just split on the clear screen ANSI code or find the last occurrence of the content.
  // Let's split by the "move to top-left" sequence if it exists.
  // Ink uses \x1b[0G\x1b[2K... to clear lines when rerendering.
  // Actually, wait, `output` is the captured stdout, we can simply rely on the last frame `lastFrame()`
  // but wait! `lastFrame()` was giving an error.
  // Let's use `waitUntilExit` and clear screen logic, or better yet, `lastFrame` IS available on the unmounted instance
  // if we do not destructure it immediately? Actually, Ink's `render` returns `lastFrame`.
  // But our node version / ink version might have it under a different name or we used `as any`.
  // Let's instead write a custom simple ANSI frame extractor.
  let finalOutput = output;
  const match = output.lastIndexOf('\x1b[0G\x1b[2K\x1b[1A');
  if (match !== -1) {
     // It's a sequence of clear line up, let's find the last sequence of clears
     const parts = output.split(/(?:\x1b\[0G\x1b\[2K\x1b\[1A)+/);
     finalOutput = parts[parts.length - 1];
  } else {
     // Check if we have two completely identical outputs separated by whitespace
     // Because Ink will render twice initially
     const halfIndex = Math.floor(output.length / 2);
     if (output.length > 10) {
         // let's do a more robust dedup. Ink appends the second frame.
         const trimmed = output.trim();
         const mid = Math.floor(trimmed.length / 2);
         const first = trimmed.slice(0, mid).trim();
         const second = trimmed.slice(mid).trim();
         if (first === second) {
             finalOutput = second;
         }
     }
  }

  finalOutput = finalOutput.trim();

  const converter = new AnsiToHtml({
    newline: true,
    escapeXML: true,
    colors: {
      0: '#000000',
      1: '#cc0000',
      2: '#4e9a06',
      3: '#c4a000',
      4: '#3465a4',
      5: '#75507b',
      6: '#06989a',
      7: '#d3d7cf',
      8: '#555753',
      9: '#ef2929',
      10: '#8ae234',
      11: '#fce94f',
      12: '#729fcf',
      13: '#ad7fa8',
      14: '#34e2e2',
      15: '#eeeeec'
    }
  });

  const htmlBody = converter.toHtml(finalOutput);

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Gemini Session</title>
  <style>
    body {
      background-color: #1e1e1e;
      color: #d4d4d4;
      font-family: 'Courier New', Courier, monospace;
      padding: 20px;
      line-height: 1.4;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
  </style>
</head>
<body>
${htmlBody}
</body>
</html>`;

  console.log(html);
}

main().catch(console.error);
