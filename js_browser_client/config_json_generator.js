$(document).on("ready", function(){

	$(".panel_configuracion").on("click", function(){
		let button_string = "Abrir panel de configuración de Fiscalberry";
		$(this).val() == button_string ? al_mostrar_panel() : al_cerrar_panel();
		$("#ConfigPanel").toggle("fade");
	});

	function al_mostrar_panel() {
	    $(".panel_configuracion").val("Cerrar panel de configuración de Fiscalberry");
	}

	function al_cerrar_panel() {
	    $(".panel_configuracion").val("Abrir panel de configuración de Fiscalberry");
	}

	$("#listadoImpresoras").on("click", ".eliminar_impresora", function(){
		let confirmacion = confirm("¿Esta seguro que desea eliminar esa impresora del config.ini?");
		if(confirmacion) {
			$(this).parent().remove();
		}
	}); 

	$("#AgregarImpresora").on("click", function(){
		var template = $("#NuevaImpresora").html();
		$("#listadoImpresoras").append(template);
	});

	
});
