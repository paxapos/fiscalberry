$(document).on("ready", function(){

	$(".panel_configuracion").on("click", function(){
		let button_string = "Abrir panel de configuración de Fiscalberry";
		$(this).val() == button_string ? al_mostrar_panel() : al_cerrar_panel();
		$("#configPanel").toggle("fade");
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

	$("#agregarImpresora").on("click", function(){
		var template = $("#nuevaImpresora").html();
		$("#listadoImpresoras").append(template);
	});

	fbrry.on("fb:rta:getActualConfig", function (ob, evt) {
        let template_for_server = $("#inputsServidor").html();
        let template_for_printer = $("#nuevaImpresora").html();
		
        for(let key in evt.data) {
        	if(key === "SERVIDOR") {
        		let puerto = evt.data[key].puerto;
        		$("#sectionServidor").append(template_for_server);
        		$("input[name='server_port']").val(puerto);
        		$("#sectionServidor").show();
        	} else {
        		let nombre_impresora = key;
        		let marca_impresora = evt.data[key].marca;
        		let driver_impresora = evt.data[key].driver;
        		let modelo_impresora = evt.data[key].modelo;
        		let host_impresora = evt.data[key].host;
        		let path_impresora = evt.data[key].path;
        		let codepage_impresora = evt.data[key].codepage;

        		$("#listadoImpresoras").append(template_for_printer);

        		let div_impresora = $("#listadoImpresoras > .impresora:last-child");
        		
        		$(div_impresora).children("input[name='nombre_impresora']").val(nombre_impresora);
        		$(div_impresora).children("select[name='marca_impresora']").val(marca_impresora).trigger("change");
        		$(div_impresora).children("select[name='driver_impresora']").val(driver_impresora).trigger("change");
        		
        		if(modelo_impresora) {
        			$(div_impresora).children(".modelo_impresora").children("input[name='modelo_impresora']").val(modelo_impresora);
        		}
        		if(host_impresora) {
        			$(div_impresora).children("select[name='tipo_conexion_impresora']").val("host").trigger("change");
        			$(div_impresora).children("input[name='host_path']").val(host_impresora);
        		}
        		if(path_impresora) {
        			$(div_impresora).children("select[name='tipo_conexion_impresora']").val("path").trigger("change");
        			$(div_impresora).children("input[name='host_path']").val(path_impresora);
        		}
        		if(codepage_impresora) {
        			$(div_impresora).children("input[name='codepage_impresora']").val(codepage_impresora);
        		}
        	}
        }

        $("#listadoImpresoras").show();
    });

    $("#listadoImpresoras").on("change", "select[name='marca_impresora']",function(){
    	if($(this).val() === "Hasar") {
    		$(this).parent().children(".modelo_impresora").show();
    	} else {
    		$(this).parent().children(".modelo_impresora").hide();
    	}
    });

    $("#listadoImpresoras").on("change", "select[name='tipo_conexion_impresora']",function(){
    	if($(this).val() === "path") {
    		$(this).parent().children(".nombre_tipo_conexion").text("Path: ");
    	} else {
    		$(this).parent().children(".nombre_tipo_conexion").text("Host: ");
    	}
    });

	
});
