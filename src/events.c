/* What the translated code asks of parts of the game that are not translated yet.
 *
 * Sound/border requests use this queue. Legacy blast APIs also retain damage and
 * removal event boundaries; newer native paths execute those game routines. A caller can read
 * the notes with game_events; the tests compare them with the calls the original makes.
 *
 * Also here: the one piece of outside information the translated code needs so far, the
 * time of day that DOS would report.
 */
#include "term.h"

#define MAX_EVENTS 512

static GameEvent events[MAX_EVENTS];
static int event_count;
static uint16_t clock_cx, clock_dx;

void event_push(uint16_t kind, uint16_t a, uint16_t b)
{
    if (event_count < MAX_EVENTS) {
        events[event_count].kind = kind;
        events[event_count].a = a;
        events[event_count].b = b;
        event_count++;
    }
}

/* Copies up to `max` pending events to `out`, forgets them all, and returns how many there
 * were (which can be more than `max`). */
int game_events(GameEvent *out, int max)
{
    int n = event_count;
    for (int i = 0; i < n && i < max; i++)
        out[i] = events[i];
    event_count = 0;
    return n;
}

/* What DOS function 2Ch would return: CX = hours:minutes, DX = seconds:hundredths. */
void game_set_clock(uint16_t cx, uint16_t dx)
{
    clock_cx = cx;
    clock_dx = dx;
}

uint16_t game_clock_cx(void)
{
    return clock_cx;
}

uint16_t game_clock_dx(void)
{
    return clock_dx;
}
