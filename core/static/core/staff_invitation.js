const invitation = location.hash.slice(1);
history.replaceState(null, '', location.pathname);
if (/^[A-Za-z0-9_-]{43}$/.test(invitation)) {
    document.getElementById('invitation').value = invitation;
    document.getElementById('confirm').disabled = false;
    document.getElementById('missing').hidden = true;
}
