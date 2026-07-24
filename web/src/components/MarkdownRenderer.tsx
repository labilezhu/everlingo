import { createContext, useContext } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export const LinkListenerContext = createContext<((url: string) => boolean) | undefined>(undefined);

export function useLinkListener() {
  return useContext(LinkListenerContext);
}

export default function MarkdownRenderer({ content }: { content: string }) {
  const linkListener = useLinkListener();
  return (
    <div className="prose prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node, href, children, ...props }) => {
            const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
              if (!href) return;
              if (linkListener?.(href)) {
                e.preventDefault();
              }
            };
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                onClick={handleClick}
                {...props}
              >
                {children}
              </a>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
