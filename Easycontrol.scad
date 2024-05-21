// Parameter für die innere Box
inner_length = 70;  // Länge der inneren Box (7cm)
inner_width = 20;   // Breite der inneren Box (2cm)
inner_height = 23;  // Höhe der inneren Box (2.3cm)
wall_thickness = 2;  // Wandstärke
bottom_thickness = 5; // Dicke des unteren Randes

// Berechnete äußere Dimensionen
outer_length = inner_length + 2 * wall_thickness;
outer_width = inner_width + 2 * wall_thickness;
outer_height = inner_height + bottom_thickness;

// Funktion, um ein Kästchen zu generieren
module box() {
    difference(){
        difference() {
            // Äußere Box
            cube([outer_length, outer_width, outer_height], center = false);
            
            // Innere Box (Subtrahiert von der äußeren Box)
            translate([wall_thickness, wall_thickness, bottom_thickness])
                cube([inner_length, inner_width, inner_height+5], center = false);
        }
        //Aussparung für USB
        translate([wall_thickness, wall_thickness, bottom_thickness+10])
                cube([inner_length+10, inner_width, inner_height], center = false);
        //Aussparung für Deckel
        translate([1, 1, outer_height-2])
            cube([outer_length-1, outer_width-2, 1], center = false);
        //Aussparung links und rechts unten
        cube([outer_length, 2.5, 1], center = false);
        translate([0, outer_width-2.5, 0])
            cube([outer_length, 2.5, 1], center = false);
        cube([2.5,outer_width, 1], center = false);
        //Ausparung für Drähte
        translate([10, 5, 0])
            cube([outer_length-20, outer_width-10, bottom_thickness], center = false);
        
        
    }
        
}


// Aufruf der Funktion
box();
