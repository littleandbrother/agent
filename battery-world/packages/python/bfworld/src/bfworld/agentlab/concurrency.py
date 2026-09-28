"""Process-safe conversation capacity; legacy batch execution stays exclusive."""
import contextlib
import fcntl
import re
from pathlib import Path

MAX_CONVERSATIONS = 3


@contextlib.contextmanager
def conversation_slot(home, owner):
    if not re.fullmatch(r'pi-chat-[a-f0-9]{16}', owner):
        raise ValueError('CONVERSATION_ID_INVALID')
    directory = Path(home) / 'conversation-locks'
    directory.mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        # A batch still owns LOCK_EX on this file. Conversations share it, but
        # keep separate owner locks and an explicit cross-process slot ceiling.
        batch = stack.enter_context((Path(home) / 'pi-session.lock').open('a'))
        try:
            fcntl.flock(batch, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('PI_BATCH_ALREADY_RUNNING') from None
        session = stack.enter_context((directory / (owner + '.lock')).open('a'))
        try:
            fcntl.flock(session, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('PI_SESSION_ALREADY_RUNNING') from None
        slot = None
        for index in range(MAX_CONVERSATIONS):
            candidate = (directory / f'slot-{index}.lock').open('a')
            try:
                fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                candidate.close()
                continue
            slot = stack.enter_context(candidate)
            break
        if slot is None:
            raise ValueError('PI_CONVERSATION_CAPACITY')
        # launch() can retain its owner-exclusive lock contract unchanged.
        yield session
