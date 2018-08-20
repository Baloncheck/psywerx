from django.core.paginator import Paginator
from django.db.models.aggregates import Count
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt
from irc.models import Irc, Link, Karma, GroupMembers
from datetime import date, timedelta, datetime
from collections import defaultdict
try:
    from local_settings import MAGIC_WORD, COOKIE_TOKEN, CHANNEL, TOKEN
except ImportError:
    from settings import MAGIC_WORD, COOKIE_TOKEN, CHANNEL, TOKEN
import hashlib
import json


def has_token(request):
    if request.POST and request.POST.has_key('token') and request.POST["token"] == TOKEN:
        return 1
    return 0

@csrf_exempt
def irc_bot_add(request):
    if not has_token(request):
        return HttpResponse("NO")
    result = Irc().parse(request.POST['raw'], request.POST['channel'])
    return HttpResponse(result)

@csrf_exempt
def karma_add(request):
    if not has_token(request):
        return HttpResponse("NO")
    Karma.objects.create(nick = request.POST['nick'], channel = request.POST['channel'])
    return HttpResponse("OK")

@csrf_exempt
def karma_nick(request):
    if not has_token(request):
        return HttpResponse("NO")
    if request.POST.has_key('nick'):
        nick = request.POST['nick']
        karmaQuery = Karma.objects.filter(nick__startswith = nick[:4], channel__iexact = request.POST['channel'], time__year = datetime.now().year)
        nicks = set(k.nick for k in karmaQuery)
        if nick in nicks:
            nicks.remove(nick)
        combined_karma = len(karmaQuery)
        karma = len(Karma.objects.filter(nick = nick, channel__iexact = request.POST['channel'], time__year = datetime.now().year))
        if combined_karma > karma:
            karma = ("%s (or %s with his other nicknames - " + ", ".join(nicks) + ")") % (karma, combined_karma)
        else:
            karma = "%s" %karma
    else:
        d = defaultdict(int)
        dn = {}
        for o in Karma.objects.all().filter(channel__iexact = request.POST['channel'], time__year = datetime.now().year).values('nick').annotate(karma=Count('nick')).order_by('-karma'):
            if o['karma'] > d[o['nick'][:4]]:
                dn[o['nick'][:4]] = o['nick']
            d[o['nick'][:4]] += o['karma']

        import operator
        sd = sorted(d.iteritems(), key=operator.itemgetter(1), reverse=True)
        k = []
        for s in sd:
            k.append({'nick': dn[s[0]], 'karma': s[1]})

        karma = json.dumps(k)

    return HttpResponse(karma)

def dump(request):
    out = [{"message": a.message, "time": str(a.time), "nick": a.nick, \
            "msg_type": a.msg_type, "msg_action": a.msg_action} for a in Irc.objects.all()]
    return HttpResponse(json.dumps(out), mimetype="application/json")

def dump_karma(request):
    out = [{"nick": a.nick, "time": str(a.time), "channel": a.channel} for a in Karma.objects.all()]
    return HttpResponse(json.dumps(out), mimetype="application/json")

def irc(request, page=1, link_page=1):
    def _remove_duplicate_nicks(karma):
        d = {}
        for k in karma:
            nick_start = k['nick'][:4]
            if nick_start not in d:
                d[nick_start] = {'nick': k['nick'], 'karma': k['karma']}
            else:
                d[nick_start]['karma'] += k['karma']
        return sorted([d[dd] for dd in d], key=lambda k:k['karma'], reverse=True)[:5]

    # Set the cookie
    if request.POST and request.POST.has_key('word') and hashlib.sha224(request.POST['word']).hexdigest() == MAGIC_WORD:
        r = HttpResponseRedirect('.')
        r.set_cookie("irctoken", COOKIE_TOKEN, 60*60*24*356*100)
        return r

    irc_token = request.COOKIES.get("irctoken", "")

    if irc_token == COOKIE_TOKEN:

        if request.POST.has_key('term'):
            q = Irc.objects.all().filter(message__icontains = request.POST['term'], channel__iexact = CHANNEL).order_by('time').reverse()
        else:
            from django.db.models import Q
            q = Irc.objects.filter(Q(channel__iexact = CHANNEL) | Q(msg_type = 'Q')).order_by('time').reverse()

        p = Paginator(q, 100)

        links = Link.objects.all().filter(irc__channel=CHANNEL).order_by('id').reverse()
        links_p = Paginator(links, 10)

        # all time:
        karma = Karma.objects.all().filter(channel__iexact = CHANNEL,time__year = datetime.now().year).values('nick').annotate(karma=Count('nick')).order_by('-karma')
        karma = _remove_duplicate_nicks(karma)

        # this week:
        week_start = date.today() - timedelta(days = date.today().weekday())
        karma_week = Karma.objects.filter(time__gte = week_start, channel__iexact = CHANNEL, time__year = datetime.now().year).values('nick').annotate(karma=Count('nick')).order_by('-karma')
        karma_week = _remove_duplicate_nicks(karma_week)

        # this month:
        month_start = date.today() - timedelta(days = date.today().day-1)
        karma_month = Karma.objects.filter(time__gte = month_start, channel__iexact = CHANNEL, time__year = datetime.now().year).values('nick').annotate(karma=Count('nick')).order_by('-karma')
        karma_month = _remove_duplicate_nicks(karma_month)


        return render_to_response('irc.html', {'log': p.page(page), 'links': links_p.page(link_page), 'karma':karma, 'karma_week':karma_week, 'karma_month':karma_month}, context_instance=RequestContext(request))
    else:
        return render_to_response('irc_access.html', {'hello': "aaa",}, context_instance=RequestContext(request))

@csrf_exempt
def join(request):
    if not has_token(request):
        return HttpResponse("NO")
    GroupMembers.join(request.POST['nick'], request.POST['group'], request.POST['offline'], request.POST['channel'])
    return HttpResponse(json.dumps("ok"), mimetype="application/json")

@csrf_exempt
def leave(request):
    if not has_token(request):
        return HttpResponse("NO")
    GroupMembers.leave(request.POST['nick'], request.POST['group'], request.POST['channel'])
    return HttpResponse(json.dumps("ok"), mimetype="application/json")

@csrf_exempt
def leaveAll(request):
    if not has_token(request):
        return HttpResponse("NO")
    GroupMembers.leaveAll(request.POST['nick'], request.POST['channel'])
    return HttpResponse(json.dumps("ok"), mimetype="application/json")

@csrf_exempt
def groups(request):
    if not has_token(request):
        return HttpResponse("NO")
    ret = GroupMembers.groups(request.POST['channel'])
    return HttpResponse(json.dumps(', '.join(ret)), mimetype="application/json")

@csrf_exempt
def mygroups(request):
    if not has_token(request):
        return HttpResponse("NO")
    ret = GroupMembers.mygroups(request.POST['channel'], request.POST['nick'])
    return HttpResponse(json.dumps(', '.join(ret)), mimetype="application/json")

@csrf_exempt
def mention(request):
    if not has_token(request):
        return HttpResponse("NO")
    members = GroupMembers.mention(request.POST['group'], request.POST['channel'])
    out = [(m.nick, m.channel, m.offline) for m in members]
    return HttpResponse(json.dumps(out), mimetype="application/json")
