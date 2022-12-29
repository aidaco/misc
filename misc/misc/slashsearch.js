// Paste into the console to enable '/' to focus search box in certain sites.
function acceptsTextInput(el) {
	if ([null, undefined].includes(el)) {
		return false
	} else if (el.getAttribute('contentEditable') === 'true') {
		return true
	} else {
		tag = el.tagName.toLowerCase()
		type = el.getAttribute('type')
		input_tags = ['input', 'textarea']
		input_types = [null, 'text', 'password', 'number', 'email', 'tel', 'url', 'search', 'date', 'datetime', 'datetime-local', 'time', 'month', 'week']
		if (input_tags.includes(tag)) {
			if (!el.hasAttribute('readonly') && input_types.includes(type)) {
				return true
			}
		}
	}
	return false
}

document.addEventListener('keydown', function(evt){
	if (evt.which == 191) {
		if (!acceptsTextInput(document.activeElement)) {
			evt.preventDefault()
			evt.stopImmediatePropagation()
			document.querySelector('#scrollable-dropdown-menu > input').focus()
		}
	}
})
