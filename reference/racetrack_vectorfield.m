% Superposition of Vector fields
x_minmax = [-1000.0, 1000.0];
y_minmax = [-1000.0, 1000.0];
ticks = 97;
scale = 0.6;

origin{1} = [+500, 300, 0];
origin{2} = [-500, -300, 0];

TotalDirection = -1;
% Loitering Factor
spd = 30.0;
Rd = 300.0;
gamma = -0.2 * TotalDirection;
% Lining Factor
k = 0.3;
course_inf_deg = atan2(Rd*10, norm(origin{1}-origin{2})) * 180/pi; % 60;

% Basis
[X, Y] = meshgrid(linspace(x_minmax(1),x_minmax(2),ticks),linspace(y_minmax(1),y_minmax(2),ticks));
R = sqrt(X.^2 + Y.^2);
[m, n] = size(X);
U = zeros(m, n);
V = zeros(m, n);
dist = zeros(m, n);
inouts = zeros(m, n);
leftrights = zeros(m, n);
section = zeros(m, n);

% Circle-Line Combination
for i = 1 : m
    for j = 1 : n
        x = X(i,j);
        y = Y(i,j);
        now = [x, y, 0];
        while(1)
            % Seperate Sections
            line_vector_between = origin{1} - origin{2};
            line_unit_vector_between = line_vector_between / max(1.0, norm(line_vector_between));
            point_on_line = (origin{1} + origin{2})/2;
            tmp = cross(line_unit_vector_between, now - point_on_line);
            leftright = 2 * (tmp(3) > 0) - 1;
            % Check Section 1 ( affected by origin{1} )
            now_trans = now - origin{1};
            dist = dot(line_unit_vector_between, now_trans);
            if dist > 0
                section(i,j) = 1;
                break;
            end
            % Check Section 2 ( affected by origin{2})
            now_trans = now - origin{2};
            dist = dot(-line_unit_vector_between, now_trans);
            if dist > 0
                section(i,j) = 2;
                break;
            end
            % Check Section 3 ( Left side of line from origin{2} to origin{1} )
            if leftright > 0
                section(i,j) = 3; % left (+) 
                break;
            else
                section(i,j) = 4; % right (-)
                break;
            end
            assert(0,"That point is not belong to any section");
            break;
        end
        switch section(i,j)
            case {1,2}
            if section(i,j) == 1
                % First Circle
                new_origin = origin{1};
            else
                % Second Circle
                new_origin = origin{2};
            end
            % Loitering
            v_rn = [0,0,1];
            v_rt = [X(i,j), Y(i,j), 0] - new_origin;
            u_rn = v_rn / max(1.0, sqrt(dot(v_rn,v_rn)));
            u_rt = v_rt / max(1.0, sqrt(dot(v_rt,v_rt)));
            rn = 0;
            rt = sqrt(dot(v_rt,v_rt));
            
            alpha = (1/spd)*sqrt(power(rn,2)+power(rt-Rd,2)+power(Rd*gamma,2));
            dVf = rn*u_rn + (rt - Rd)*u_rt;
            Contraction = dVf / alpha;
            Circular = gamma * rt * cross(u_rn, u_rt) / alpha;
            h = -Contraction + Circular;
            course_cmd_deg = atan2(h(2),h(1)) * 180/pi;
            U(i,j) = U(i,j) + h(1);
            V(i,j) = V(i,j) + h(2);

            case {3,4}
            % Line
            normal_vector = cross(line_unit_vector_between, [0,0,1]);
            normal_vector = normal_vector / norm(normal_vector);
            point_on_side_line = point_on_line - Rd * leftright * normal_vector;
            now_trans = now - point_on_side_line;
            dist = leftright * dot(now_trans, normal_vector);
            % Inner? Outer?
            inout = 2 * (dist > 0) - 1;
            inouts(i,j) = inout;
            leftrights(i,j) = leftright;

            slope_angle_deg = atan2(TotalDirection*leftright*line_unit_vector_between(2),TotalDirection*leftright*line_unit_vector_between(1))*180/pi;
            now_trans = now - point_on_side_line;
            dist = sqrt(abs(dot(now_trans,leftright * normal_vector)));
            course_cmd_deg =  (slope_angle_deg + TotalDirection * inout * course_inf_deg * (2/pi) * atan(k * dist));
            
            U(i,j) = U(i,j) + spd * cosd(course_cmd_deg);
            V(i,j) = V(i,j) + spd * sind(course_cmd_deg);
        end
    end
end

figure(1);
quiver(X,Y,U,V,scale);
xlim(x_minmax); ylim(y_minmax);
hold on;
grid on;

% Points on vector field
dt = 0.2;
EndTime = 50;
p{1} = [200, 200, 0];
p{2} = [ 50,  50, 0];
p{3} = [  0, 200, 0];
for j = 1 : length(p)
    for i = 2 : (EndTime/dt)
        px = p{j}(i-1,1) + dt * interp2(X,Y,U,p{j}(i-1,1),p{j}(i-1,2));
        py = p{j}(i-1,2) + dt * interp2(X,Y,V,p{j}(i-1,1),p{j}(i-1,2));
        pz = 0.0;
        if ((x_minmax(1) > px) || (px > x_minmax(2)))
            break;
        end
        if ((y_minmax(1) > py) || (py > y_minmax(2)))
            break;
        end
        p{j}(i,1) = px;
        p{j}(i,2) = py;
        p{j}(i,3) = pz;
    end
end
for j = 1 : length(p)
    plot(p{j}(:,1),p{j}(:,2),'LineWidth',3);
end
for j = 1 : length(origin)
    plot(origin{j}(1), origin{j}(2),'ro');
    plot(cosd(0:15:360)*Rd+origin{j}(1),sind(0:15:360)*Rd+origin{j}(2),'r:');
end
plot([origin{1}(1), origin{2}(1)],[origin{1}(2), origin{2}(2)],'r:');
hold off;
% inouts