import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import type { TaskKind } from '@/types/chat';

export default function TaskSelector({
  task,
  onChange,
}: {
  task: TaskKind;
  onChange: (t: TaskKind) => void;
}) {
  const { t } = useTranslation('chatbot');
  const TASKS: { value: TaskKind; label: string }[] = [
    { value: 'translate', label: t('task_translate') },
    { value: 'look_up', label: t('task_look_up') },
    { value: 'none', label: t('task_chat') },
  ];
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
