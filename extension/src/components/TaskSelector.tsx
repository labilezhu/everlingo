import { Button } from '@/components/ui/button';
import type { TaskKind } from '@/types/envelope';

const TASKS: { value: TaskKind; label: string }[] = [
  { value: 'translate', label: '翻译' },
  { value: 'look_up', label: '查词' },
  { value: 'none', label: '聊天' },
];

export default function TaskSelector({
  task,
  onChange,
}: {
  task: TaskKind;
  onChange: (t: TaskKind) => void;
}) {
  return (
    <div className="flex gap-1 px-3 py-2 border-b border-border">
      {TASKS.map((t) => (
        <Button
          key={t.value}
          size="sm"
          variant={task === t.value ? 'default' : 'outline'}
          onClick={() => onChange(t.value)}
        >
          {t.label}
        </Button>
      ))}
    </div>
  );
}
