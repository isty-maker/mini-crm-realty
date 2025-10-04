(function () {
  function storeInitialDisabled(control) {
    if (control.dataset.initialDisabled === undefined) {
      control.dataset.initialDisabled = control.disabled ? 'true' : 'false';
    }
  }

  function setDisabled(section, shouldDisable) {
    var controls = section.querySelectorAll('input, select, textarea');
    controls.forEach(function (control) {
      storeInitialDisabled(control);
      if (shouldDisable) {
        control.disabled = true;
      } else if (control.dataset.initialDisabled === 'true') {
        control.disabled = true;
      } else {
        control.disabled = false;
      }
    });
  }

  function normalizeType(type) {
    return (type || '').trim();
  }

  function showSection(type) {
    var target = normalizeType(type);
    var sections = document.querySelectorAll('[data-section]');
    sections.forEach(function (section) {
      var dataset = (section.dataset.section || '').split(',').map(function (value) {
        return value.trim();
      }).filter(Boolean);
      var match = target && dataset.includes(target);
      if (match) {
        section.hidden = false;
        setDisabled(section, false);
      } else {
        section.hidden = true;
        setDisabled(section, true);
      }
    });
  }

  function currentCategory() {
    var categoryField = document.getElementById('id_category');
    return categoryField ? categoryField.value : '';
  }

  function handleChange() {
    showSection(currentCategory());
  }

  document.addEventListener('DOMContentLoaded', function () {
    var categoryField = document.getElementById('id_category');
    var subtypeField = document.getElementById('id_subtype');
    handleChange();
    [categoryField, subtypeField].forEach(function (field) {
      if (field) {
        field.addEventListener('change', handleChange);
      }
    });
  });
})();
